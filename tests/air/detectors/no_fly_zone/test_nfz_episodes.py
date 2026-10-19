"""Episode grouping tests - logic/episodes.py, plus the real-data slice.

Unit tests drive group_episodes with hand-built per-report detections so each
close rule is pinned on its own. The last tests run the whole pipeline on
fixtures/tracks/lynchburg_crossings.csv: the raw rows of two real crossings of
fixture zone P-901 from data/lynchburg_adsb.csv.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from nfz_support import AIRSPACE_FILE, FIXTURES

from air.detectors.no_fly_zone.config import Config
from air.detectors.no_fly_zone.ingest.adsb_loader import load_states
from air.detectors.no_fly_zone.ingest.airspace_loader import load_zones
from air.detectors.no_fly_zone.logic.detector import run
from air.detectors.no_fly_zone.logic.episodes import group_episodes
from air.detectors.no_fly_zone.types import Detection, ReportResult, Severity

CROSSINGS_FILE = FIXTURES / "tracks" / "lynchburg_crossings.csv"
T0 = datetime(2026, 9, 1, 0, 54, 46, tzinfo=UTC)


def _det(
    at: datetime,
    *,
    zone: str = "P-901",
    severity: Severity = Severity.HIGH,
    score: float = 0.9,
    row: str = "r",
    signals: Sequence[str] = (),
    limitations: Sequence[str] = (),
    penetration: float | None = 0.5,
) -> Detection:
    extras: dict[str, Any] = {
        "observed_at": at, "source_row_id": row, "lat": 37.42, "lon": -79.21,
        "zone_id": zone, "zone_type": "PROHIBITED", "signal_facts": list(signals),
    }
    if penetration is not None:
        extras["penetration_nm"] = penetration
    return Detection(
        detector_id="skywatch.no_fly_zone", detector_version="0.1.0",
        entity_ids=("aircraft:a89076",), detection_type="restricted_airspace_incursion",
        severity=severity, anomaly_score=score,
        raw_model_confidence=1.0 if severity is Severity.HIGH else 0.0,
        evidence_refs=(f"adsb:{row}", f"airspace:{zone}"),
        feature_schema_version="air-features-v1", baseline_or_model_version="test",
        explanation_facts=(f"fact for {row}",) + tuple(signals),
        limitations=tuple(limitations), extras=extras,
    )


def _report(seconds: float, *fired: Detection, icao: str = "a89076") -> ReportResult:
    return ReportResult(icao, T0 + timedelta(seconds=seconds), tuple(fired))


def _hit(seconds: float, **kw: Any) -> ReportResult:
    at = T0 + timedelta(seconds=seconds)
    return _report(seconds, _det(at, row=f"r{seconds:g}", **kw))


def _clear(seconds: float, icao: str = "a89076") -> ReportResult:
    return _report(seconds, icao=icao)


def test_a_crossing_becomes_one_episode(cfg: Config) -> None:
    """Entry, 5 inside reports, 2 clear reports: one Detection spanning the
    first to the last firing report."""
    reports = [_hit(2.0 * i) for i in range(6)] + [_clear(12), _clear(14)]
    (episode,) = list(group_episodes(reports, cfg))

    assert episode.extras["report_count"] == 6
    assert episode.extras["episode_start"] == T0
    assert episode.extras["episode_end"] == T0 + timedelta(seconds=10)
    assert episode.extras["dwell_sec"] == 10.0
    assert episode.extras["entry_source_row_id"] == "r0"
    assert episode.extras["exit_source_row_id"] == "r10"
    assert episode.explanation_facts[0].startswith(
        "Aircraft a89076 was in zone P-901 (PROHIBITED) for 10 s across 6 reports"
    )


def test_one_clear_report_does_not_split_the_episode(cfg: Config) -> None:
    """A single non-firing fix (boundary jitter) is not an exit."""
    reports = [_hit(0), _hit(2), _clear(4), _hit(6), _hit(8)]
    (episode,) = list(group_episodes(reports, cfg))
    assert episode.extras["report_count"] == 4


def test_riding_the_boundary_stays_one_episode(cfg: Config) -> None:
    """In, out, in, out, in: every hit resets the clear count, so isolated
    clear fixes never add up to an exit."""
    reports = [_hit(0), _clear(2), _hit(4), _clear(6), _hit(8)]
    (episode,) = list(group_episodes(reports, cfg))
    assert episode.extras["report_count"] == 3


def test_two_clear_reports_close_it(cfg: Config) -> None:
    reports = [_hit(0), _hit(2), _clear(4), _clear(6), _hit(8), _hit(10)]
    episodes = list(group_episodes(reports, cfg))
    assert [e.extras["report_count"] for e in episodes] == [2, 2]


def test_silence_longer_than_max_gap_closes_it(cfg: Config) -> None:
    gap = float(cfg["sampling"]["max_gap_sec"])
    reports = [_hit(0), _hit(2), _hit(2 + gap + 1)]
    assert [e.extras["report_count"] for e in group_episodes(reports, cfg)] == [2, 1]


def test_a_slow_reporter_inside_the_gap_stays_one_episode(cfg: Config) -> None:
    """N90508's pattern: reports 6 s apart, buffer-only INFO then inside HIGH."""
    reports = [
        _hit(0, severity=Severity.INFO, score=0.900, penetration=None),
        _hit(6, severity=Severity.HIGH, score=0.9002),
        _clear(17), _clear(22),
    ]
    (episode,) = list(group_episodes(reports, cfg))
    assert episode.severity is Severity.HIGH
    assert episode.extras["report_count"] == 2


def test_peak_score_and_highest_severity_are_kept_separately(cfg: Config) -> None:
    """A buffer-only report can carry the peak score while a strictly-inside
    report carries the severity; the episode keeps both."""
    reports = [
        _hit(0, severity=Severity.INFO, score=0.90, penetration=None),
        _hit(2, severity=Severity.HIGH, score=0.51, penetration=1.2),
        _hit(4, severity=Severity.HIGH, score=0.50, penetration=0.4),
    ]
    (episode,) = list(group_episodes(reports, cfg))

    assert episode.anomaly_score == 0.90
    assert episode.severity is Severity.HIGH
    assert episode.raw_model_confidence == 1.0
    assert episode.extras["penetration_nm"] == 1.2      # deepest, not the representative's
    assert episode.extras["peak_score_at"] == T0
    assert episode.explanation_facts[1] == "fact for r2"  # the worst moment's facts


def test_a_signal_that_appears_later_is_reported_with_when(cfg: Config) -> None:
    """PDT5877's pattern: squawk 2240 shows up 14 s into the crossing."""
    squawk = "squawk 2240 is a discrete beacon code"
    reports = [_hit(0, score=0.91), _hit(14, score=0.51, signals=[squawk])]
    (episode,) = list(group_episodes(reports, cfg))

    assert episode.anomaly_score == 0.91
    assert f"{squawk} (first seen 00:55:00, 14 s after entry)." in episode.explanation_facts


def test_limitations_and_evidence_are_unioned(cfg: Config) -> None:
    baro = "Only barometric altitude was available; geometric altitude was unavailable."
    reports = [_hit(0), _hit(2, limitations=[baro]), _hit(4, score=0.95), _hit(6)]
    (episode,) = list(group_episodes(reports, cfg))

    assert episode.limitations == (baro,)
    assert episode.evidence_refs == ("adsb:r0", "airspace:P-901", "adsb:r4", "adsb:r6")


def test_each_zone_and_each_aircraft_gets_its_own_episode(cfg: Config) -> None:
    both = _report(
        0, _det(T0, zone="P-901", row="a"), _det(T0, zone="TFR-6/1234", row="b")
    )
    other = replace(_hit(1), icao24="A1B2C3")
    episodes = list(group_episodes([both, other], cfg))

    keys = sorted((e.entity_ids[0], e.extras["zone_id"]) for e in episodes)
    assert len(keys) == 3 and ("aircraft:a89076", "TFR-6/1234") in keys


def test_an_episode_still_open_at_the_end_is_emitted(cfg: Config) -> None:
    (episode,) = list(group_episodes([_hit(0), _hit(2)], cfg))
    assert episode.extras["episode_end"] == T0 + timedelta(seconds=2)


def test_out_of_order_reports_are_refused(cfg: Config) -> None:
    with pytest.raises(ValueError, match="not time-ordered"):
        list(group_episodes([_hit(4), _hit(2)], cfg))


def test_no_reports_no_episodes(cfg: Config) -> None:
    assert list(group_episodes([], cfg)) == []


# ------------------------------------------------- real data: two crossings


def test_lynchburg_crossings_per_report_vs_episodes(cfg: Config) -> None:
    """The raw rows of PDT5877 and N90508 crossing P-901: 21 per-report
    detections collapse to 2 episodes."""
    zones = load_zones(AIRSPACE_FILE)
    per_report = list(run(load_states(CROSSINGS_FILE), zones, cfg, per_report=True))
    episodes = {e.entity_ids[0]: e for e in run(load_states(CROSSINGS_FILE), zones, cfg)}

    assert len(per_report) == 21
    assert set(episodes) == {"aircraft:a89076", "aircraft:ac8438"}

    jet = episodes["aircraft:a89076"]                    # PDT5877
    assert jet.severity is Severity.HIGH
    assert jet.extras["report_count"] == 19
    assert jet.extras["dwell_sec"] == pytest.approx(41.3, abs=0.1)
    assert jet.anomaly_score == pytest.approx(0.909, abs=0.001)
    assert any("squawk 2240" in f and "14 s after entry" in f for f in jet.explanation_facts)

    small = episodes["aircraft:ac8438"]                  # N90508
    assert small.severity is Severity.HIGH
    assert small.extras["report_count"] == 2
    assert small.extras["dwell_sec"] == pytest.approx(6.0, abs=0.1)


def test_episode_time_bounds_reach_the_platform_record(cfg: Config) -> None:
    from air.detectors.no_fly_zone.emit import to_platform_detection

    zones = load_zones(AIRSPACE_FILE)
    jet = next(e for e in run(load_states(CROSSINGS_FILE), zones, cfg)
               if e.entity_ids == ("aircraft:a89076",))
    bounds = to_platform_detection(jet).temporal_bounds

    assert bounds.start_time is not None and bounds.end_time is not None
    span = bounds.end_time - bounds.start_time
    assert span.total_seconds() == pytest.approx(41.3, abs=0.1)
