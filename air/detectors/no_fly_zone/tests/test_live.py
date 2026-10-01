"""Live Flys Down integration - live/feed.py, live/zones.py, live/report.py.

Fixtures only: fixtures/flysdown/ holds a recorded-shape /api/aircraft
response with one hand-placed aircraft per outcome, stale and unavailable
variants, and a trimmed copy of Flys Down's zones.json. No network.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from ..config import Config
from ..live.feed import FRESH, STALE, TIMESTAMP_BASIS, UNAVAILABLE, map_feed
from ..live.readsb import TIMESTAMP_BASIS as DIRECT_BASIS
from ..live.readsb import map_readsb
from ..live.report import BUFFERED, CONFIRMED, UNCERTAIN, build_report
from ..live.runner import load_live_config, main
from ..live.text import render_text
from ..live.zones import map_zones
from ..types import Activation, Datum, ZoneType

FLYSDOWN = Path(__file__).resolve().parent.parent / "fixtures" / "flysdown"
FETCHED_AT = datetime(2026, 9, 29, 22, 30, tzinfo=UTC)
RECEIVED_AT = FETCHED_AT + timedelta(seconds=3)


def _load(name: str) -> Any:
    return json.loads((FLYSDOWN / name).read_text())


@pytest.fixture
def live_cfg() -> dict[str, Any]:
    return load_live_config()


@pytest.fixture
def report(cfg: Config, live_cfg: dict[str, Any]) -> dict[str, Any]:
    feed, zones = _load("aircraft_klyh.json"), _load("zones.json")
    return build_report(feed, zones, cfg, live_cfg, RECEIVED_AT)


# ---------------------------------------------------------------- feed mapping

def test_feed_record_maps_fields_and_provenance(cfg: Config, live_cfg: dict[str, Any]) -> None:
    batch = map_feed(_load("aircraft_klyh.json"), RECEIVED_AT, live_cfg["feed"], cfg["scope"])
    assert batch.status.status == FRESH
    state = next(s for s in batch.states if s.icao24 == "a11111")
    assert (state.lat, state.lon) == (38.89098, -77.02641)
    assert state.alt_baro_ft == 1500.0 and state.alt_geom_ft == 1600.0
    assert state.callsign == "FIXCONF" and state.squawk == "1200"
    assert state.nic is None and state.nac_p is None  # the feed does not carry them
    assert state.source_row_id == "flysdown:relay/adsb.fi:1790721000000:a11111"


def test_observation_time_is_an_estimate_that_says_so(
    cfg: Config, live_cfg: dict[str, Any]
) -> None:
    """fetchedAt minus seenPos, labeled as an estimate - never the fetch time."""
    batch = map_feed(_load("aircraft_klyh.json"), RECEIVED_AT, live_cfg["feed"], cfg["scope"])
    state = next(s for s in batch.states if s.icao24 == "a11111")
    assert state.timestamp == FETCHED_AT - timedelta(seconds=0.5)
    timing = batch.timing[state.source_row_id]
    assert timing.basis == TIMESTAMP_BASIS
    assert timing.position_age_s == pytest.approx(3.5)


def test_untimed_stale_and_out_of_scope_records_are_skipped(
    cfg: Config, live_cfg: dict[str, Any]
) -> None:
    batch = map_feed(_load("aircraft_klyh.json"), RECEIVED_AT, live_cfg["feed"], cfg["scope"])
    assert batch.skipped == {"no_position_age": 1, "stale_position": 1, "outside_scope": 1}
    ids = {s.icao24 for s in batch.states}
    assert not ids & {"a55555", "a66666", "a88888"}


def test_stale_and_unavailable_feeds_yield_no_states(live_cfg: dict[str, Any]) -> None:
    stale = map_feed(_load("aircraft_klyh_stale.json"), RECEIVED_AT, live_cfg["feed"])
    assert stale.status.status == STALE and stale.states == ()
    old = map_feed(_load("aircraft_klyh.json"), FETCHED_AT + timedelta(minutes=5), live_cfg["feed"])
    assert old.status.status == STALE and "old" in (old.status.reason or "")
    down = map_feed(_load("aircraft_unavailable.json"), RECEIVED_AT, live_cfg["feed"])
    assert down.status.status == UNAVAILABLE and "refused" in (down.status.reason or "")
    garbage = map_feed("<html>", RECEIVED_AT, live_cfg["feed"])
    assert garbage.status.status == UNAVAILABLE


# ---------------------------------------------------------------- zones

def test_zones_map_activation_honestly(live_cfg: dict[str, Any]) -> None:
    batch = map_zones(_load("zones.json"), live_cfg["zones"])
    zones = {z.zone_id: z for z in batch.zones}
    assert zones["faa-p-56-8"].activation is Activation.ALWAYS
    assert "CONTINUOUS" in batch.activation_basis["faa-p-56-8"]
    assert zones["faa-p-56-8"].ceiling_ft == 18000.0
    assert zones["faa-p-56-8"].floor_datum is Datum.SFC
    # No activation data means NOTAM (-> UNKNOWN), never active.
    assert zones["fixture-tfr-lyh"].activation is Activation.NOTAM
    assert zones["fixture-tfr-lyh"].zone_type is ZoneType.TFR
    assert {zone_id for zone_id, _ in batch.skipped} == {"dc-sfra", "demo-gulf-lane"}
    assert str(batch.asof) == "2026-09-17"


def test_distrusting_published_schedules_makes_everything_unknown(
    live_cfg: dict[str, Any],
) -> None:
    zones_cfg = dict(live_cfg["zones"], trust_published_continuous=False)
    batch = map_zones(_load("zones.json"), zones_cfg)
    assert {z.activation for z in batch.zones} == {Activation.NOTAM}


def test_zones_that_are_not_a_featurecollection_are_an_error(live_cfg: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        map_zones({"features": []}, live_cfg["zones"])


# ---------------------------------------------------------------- detector output

def test_one_input_produces_a_confirmed_active_detection(report: dict[str, Any]) -> None:
    assert report["feed"]["status"] == FRESH
    assert report["evaluation"]["ran"] is True
    confirmed = [d for d in report["detections"] if d["classification"] == CONFIRMED]
    assert len(confirmed) == 1
    det = confirmed[0]
    assert det["aircraftId"] == "a11111" and det["zoneId"] == "faa-p-56-8"
    assert det["severity"] == "HIGH" and det["confidence"] == 1.0
    assert det["activation"] == "ACTIVE"
    assert det["altitudeSource"] == "GEOMETRIC" and det["altitudeFt"] == 1600.0
    assert det["observedAtBasis"] == TIMESTAMP_BASIS
    assert det["sourceRowId"].endswith(":a11111")
    assert any("CONTINUOUS" in fact for fact in det["explanation"])
    assert any("estimated" in lim for lim in det["limitations"])


def test_unknown_activation_is_reported_as_uncertain_and_capped(report: dict[str, Any]) -> None:
    uncertain = [d for d in report["detections"] if d["classification"] == UNCERTAIN]
    assert [d["aircraftId"] for d in uncertain] == ["a33333"]
    assert uncertain[0]["severity"] == "LOW"
    assert uncertain[0]["confidence"] == 0.0
    assert uncertain[0]["activation"] == "UNKNOWN"
    assert "Zone activation could not be determined." in uncertain[0]["limitations"]


def test_buffered_only_is_its_own_class(report: dict[str, Any]) -> None:
    buffered = [d for d in report["detections"] if d["classification"] == BUFFERED]
    assert [d["aircraftId"] for d in buffered] == ["a99999"]
    assert buffered[0]["severity"] == "INFO"


def test_quiet_states_are_explained_by_exit_reasons(report: dict[str, Any]) -> None:
    ev = report["evaluation"]
    assert ev["statesEvaluated"] == 6
    assert ev["exits"] == {"no_candidate": 1, "on_ground": 1, "vertical_clear": 1}
    assert (ev["confirmedActive"], ev["activationUncertain"], ev["bufferedOnly"]) == (1, 1, 1)
    assert report["detector"]["baseline"] == "nfz-rules-0.1.0+sua-2026-09-17"


def test_a_quiet_fresh_run_differs_from_a_stale_or_failed_one(
    cfg: Config, live_cfg: dict[str, Any]
) -> None:
    """Zero detections from an evaluated feed is not the same answer as zero
    detections because nothing was evaluated."""
    quiet_payload = _load("aircraft_klyh.json")
    quiet_payload["aircraft"] = [a for a in quiet_payload["aircraft"] if a["id"] == "a77777"]
    zones = _load("zones.json")
    quiet = build_report(quiet_payload, zones, cfg, live_cfg, RECEIVED_AT)
    stale = build_report(_load("aircraft_klyh_stale.json"), zones, cfg, live_cfg, RECEIVED_AT)
    failed = build_report(_load("aircraft_unavailable.json"), zones, cfg, live_cfg, RECEIVED_AT)

    assert quiet["detections"] == stale["detections"] == failed["detections"] == []
    assert quiet["evaluation"]["ran"] is True and quiet["feed"]["status"] == FRESH
    assert quiet["evaluation"]["exits"] == {"no_candidate": 1}
    assert stale["evaluation"]["ran"] is False and stale["feed"]["status"] == STALE
    assert failed["evaluation"]["ran"] is False and failed["feed"]["status"] == UNAVAILABLE
    assert "feed stale" in stale["evaluation"]["reason"]


def test_missing_zones_means_not_evaluated(cfg: Config, live_cfg: dict[str, Any]) -> None:
    out = build_report(
        _load("aircraft_klyh.json"), None, cfg, live_cfg, RECEIVED_AT, zones_error="HTTP 503"
    )
    assert out["evaluation"]["ran"] is False
    assert "zones unavailable" in out["evaluation"]["reason"]


def test_report_is_json_and_labeled_experimental(report: dict[str, Any]) -> None:
    encoded = json.dumps(report)
    assert report["experimental"] is True
    assert any("Not for navigation" in lim for lim in report["limitations"])
    assert json.loads(encoded)["schema"] == "skywatch.flysdown.report/1"


def test_runner_replays_fixtures_without_network(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    code = main([
        "--once",
        "--source", "flysdown",
        "--feed-file", str(FLYSDOWN / "aircraft_klyh.json"),
        "--zones-file", str(FLYSDOWN / "zones.json"),
        "--out", str(out),
    ])
    assert code == 0
    written = json.loads(out.read_text())
    # Replayed long after its fetch time, the snapshot is honestly stale.
    assert written["feed"]["status"] == STALE
    assert written["evaluation"]["ran"] is False


def test_publish_without_a_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKYWATCH_TOKEN", raising=False)
    assert main(["--once", "--publish", "http://127.0.0.1:9"]) == 2


def test_each_detection_publishes_a_score_breakdown_that_adds_up(report: dict[str, Any]) -> None:
    """Anyone reading the raw report can rebuild the score from its parts."""
    for det in report["detections"]:
        s = det["scoring"]
        assert s["unclamped"] == pytest.approx(s["base"] + s["depthBump"] - s["contextPenalty"])
        assert s["score"] == pytest.approx(min(1.0, max(0.0, s["unclamped"])))
        assert s["score"] == pytest.approx(det["score"], abs=1e-3)
    confirmed = next(d for d in report["detections"] if d["classification"] == CONFIRMED)
    assert confirmed["scoring"]["base"] == 0.9  # PROHIBITED, from config.yaml
    assert confirmed["scoring"]["severityCaps"] == []
    uncertain = next(d for d in report["detections"] if d["classification"] == UNCERTAIN)
    assert uncertain["scoring"]["severityCaps"] == ["activation unknown: capped at LOW"]
    buffered = next(d for d in report["detections"] if d["classification"] == BUFFERED)
    assert buffered["scoring"]["severityCaps"][0].startswith("outside the polygon")


# ---------------------------------------------------------------- run it yourself

def test_direct_aggregator_records_map_with_nic_and_tighter_timing(
    cfg: Config, live_cfg: dict[str, Any]
) -> None:
    batch = map_readsb(_load("readsb_klyh.json"), RECEIVED_AT, live_cfg["feed"], cfg["scope"])
    assert batch.status.status == FRESH and batch.status.via == "direct"
    state = next(s for s in batch.states if s.icao24 == "a11111")
    assert state.callsign == "FIXCONF"  # trailing space trimmed
    assert state.nic == 8 and state.nac_p == 9  # carried, unlike the Flys Down feed
    assert state.timestamp == FETCHED_AT - timedelta(seconds=0.5)
    assert batch.timing[state.source_row_id].basis == DIRECT_BASIS
    ground = next(s for s in batch.states if s.icao24 == "a44444")
    assert ground.on_ground is True and ground.alt_baro_ft is None
    assert batch.skipped == {"no_position_age": 1, "stale_position": 1, "outside_scope": 1}


def test_direct_run_produces_the_same_classes(cfg: Config, live_cfg: dict[str, Any]) -> None:
    out = build_report(
        _load("readsb_klyh.json"), _load("zones.json"), cfg, live_cfg, RECEIVED_AT,
        source="adsb.lol",
    )
    classes = sorted(d["classification"] for d in out["detections"])
    assert classes == sorted([CONFIRMED, UNCERTAIN, BUFFERED])
    confirmed = next(d for d in out["detections"] if d["classification"] == CONFIRMED)
    assert any("aggregator" in lim for lim in confirmed["limitations"])
    assert out["feed"]["via"] == "direct"


def test_old_or_broken_aggregator_answers_are_not_evaluated(
    cfg: Config, live_cfg: dict[str, Any]
) -> None:
    zones = _load("zones.json")
    late = build_report(_load("readsb_klyh.json"), zones, cfg, live_cfg,
                        FETCHED_AT + timedelta(minutes=2), source="adsb.lol")
    assert late["feed"]["status"] == STALE and late["evaluation"]["ran"] is False
    broken = build_report({"msg": "rate limited"}, zones, cfg, live_cfg, RECEIVED_AT,
                          source="adsb.lol")
    assert broken["feed"]["status"] == UNAVAILABLE and broken["detections"] == []


def test_text_report_shows_the_arithmetic_and_keeps_the_rules(
    report: dict[str, Any], cfg: Config, live_cfg: dict[str, Any]
) -> None:
    text = render_text(report)
    assert "EXPERIMENTAL - not for navigation" in text
    assert "score = base 0.900 (zone type PROHIBITED) + depth 0.002" in text
    assert "severity activation unknown: capped at LOW" in text
    stale = build_report(_load("aircraft_klyh_stale.json"), _load("zones.json"), cfg, live_cfg,
                         RECEIVED_AT)
    stale_text = render_text(stale)
    assert "NOT EVALUATED" in stale_text and "not the same as finding nothing" in stale_text
    assert "score =" not in stale_text


def test_runner_prints_a_text_report_from_a_saved_aggregator_answer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = main([
        "--once",
        "--source", "adsb.lol",
        "--feed-file", str(FLYSDOWN / "readsb_klyh.json"),
        "--zones-file", str(FLYSDOWN / "zones.json"),
    ])
    assert code == 0
    printed = capsys.readouterr().out
    # Replayed long after its 'now', the answer is honestly too old to evaluate.
    assert "NOT EVALUATED" in printed
