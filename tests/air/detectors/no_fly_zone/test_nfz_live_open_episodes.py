"""Lead tests - live mode: incursions reach the store on entry, not on exit.

``build_live_detector()`` (what ``scripts/run_live_detector.py`` builds) also
returns open episodes that grew in a window, marked OPEN with no end time. The
tests pin the properties the live store relies on:

* an incursion is emitted in the first window that sees it;
* every OPEN snapshot and the final CLOSED episode share one dedup key, so an
  upsert on that key keeps one row per incursion;
* a snapshot never closes or splits an episode, and an episode with no new
  reports is not re-emitted;
* the default detector (replay, CLI) is unchanged: finished episodes only.
"""
from __future__ import annotations

import dataclasses
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

# Before the detector imports, which need both: a machine without them should
# skip this file, not fail to collect it.
pytest.importorskip("shapely")
pytest.importorskip("h3")

from air.detectors.no_fly_zone import build_detector, build_live_detector  # noqa: E402

# Unit tests pin the hand-built zones; the live default is the real FAA file.
FIXTURE_ZONES = (Path(__file__).resolve().parents[4]
                 / "air/detectors/no_fly_zone/fixtures/airspace/klyh-150nm.geojson")
from air.detectors.no_fly_zone.adapter import NoFlyZoneDetector  # noqa: E402
from air.models.observation import AdsbObservation  # noqa: E402
from air.windowing import detection_dedup_key  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[4]
_TS = datetime(2026, 9, 22, 20, 15, tzinfo=UTC)


def make_obs(**overrides: Any) -> AdsbObservation:
    """An AdsbObservation inside fixture zone P-901, below its ceiling."""
    base: dict[str, Any] = {
        "icao24": "a1b2c3",
        "observed_at": _TS,
        "latitude": 37.425,
        "longitude": -79.215,
        "altitude_ft": 4850.0,
        "alt_geom_ft": 5200.0,
        "ground_speed_kt": 186.7,
        "track_deg": 4.9,
        "callsign": "TEST123",
        "squawk": "1200",
        "emitter_category": "A3",
        "nic": 8,
        "nacp": 9,
        "on_ground": False,
        "source_row_id": "test.csv:7",
    }
    base.update(overrides)
    return AdsbObservation(**base)


def outside(seconds: int, **overrides: Any) -> AdsbObservation:
    """The same aircraft, ``seconds`` after _TS, outside every fixture zone."""
    return make_obs(
        latitude=36.0, longitude=-81.0, observed_at=_TS + timedelta(seconds=seconds),
        source_row_id=f"test.csv:out{seconds}", **overrides,
    )


def inside(seconds: int) -> AdsbObservation:
    return make_obs(
        observed_at=_TS + timedelta(seconds=seconds), source_row_id=f"test.csv:in{seconds}"
    )


@pytest.fixture
def live() -> NoFlyZoneDetector:
    return build_live_detector(airspace_path=FIXTURE_ZONES)


def test_live_factory_turns_on_open_episodes() -> None:
    assert build_live_detector(airspace_path=FIXTURE_ZONES).emit_open is True
    assert build_detector().emit_open is False


def test_incursion_is_emitted_on_entry(live: NoFlyZoneDetector) -> None:
    [entry] = live.detect_observations([inside(0)])
    extras = entry.metadata["extras"]
    assert extras["episode_status"] == "OPEN"
    assert extras["episode_end"] is None
    assert extras["report_count"] == 1
    assert entry.temporal_bounds.start_time == _TS
    assert entry.temporal_bounds.end_time is None
    summary = entry.evidence[0].summary
    assert summary is not None
    assert "still inside" in summary
    assert live.open_episodes == 1  # the snapshot did not close it


def test_open_snapshots_and_the_closed_episode_share_one_dedup_key(live: NoFlyZoneDetector) -> None:
    [first] = live.detect_observations([inside(0)])
    [second] = live.detect_observations([inside(5), inside(10)])
    [closed] = live.detect_observations([outside(11), outside(12)])

    assert second.metadata["extras"]["episode_status"] == "OPEN"
    assert second.metadata["extras"]["report_count"] == 3
    assert second.metadata["extras"]["dwell_sec"] == 10.0

    assert closed.metadata["extras"]["episode_status"] == "CLOSED"
    assert closed.metadata["extras"]["report_count"] == 3
    assert closed.temporal_bounds.end_time == _TS + timedelta(seconds=10)

    keys = {detection_dedup_key(d) for d in (first, second, closed)}
    assert len(keys) == 1, "an upsert on the dedup key must keep one row per incursion"
    assert live.open_episodes == 0


def test_an_episode_with_no_new_reports_is_not_re_emitted(live: NoFlyZoneDetector) -> None:
    assert len(live.detect_observations([inside(0)])) == 1
    # Another aircraft moves the stream on; ours sends nothing (well inside max_gap_sec).
    other = make_obs(icao24="ffffff", latitude=36.0, longitude=-81.0,
                     observed_at=_TS + timedelta(seconds=2), source_row_id="test.csv:other")
    assert live.detect_observations([other]) == []
    assert live.open_episodes == 1


def test_an_episode_is_re_emitted_when_reports_resume(live: NoFlyZoneDetector) -> None:
    """A quiet window must not stop later snapshots: the live row keeps updating."""
    [first] = live.detect_observations([inside(0)])
    other = make_obs(icao24="ffffff", latitude=36.0, longitude=-81.0,
                     observed_at=_TS + timedelta(seconds=2), source_row_id="test.csv:other")
    assert live.detect_observations([other]) == []
    [resumed] = live.detect_observations([inside(5)])
    assert resumed.metadata["extras"]["episode_status"] == "OPEN"
    assert resumed.metadata["extras"]["report_count"] == 2
    assert detection_dedup_key(resumed) == detection_dedup_key(first)


def test_overlapping_zones_get_distinct_dedup_keys(live: NoFlyZoneDetector) -> None:
    """One aircraft in two zones is two incursions, so two rows after an upsert."""
    p901 = next(zone for zone in live.zones if zone.zone_id == "P-901")
    twin = dataclasses.replace(p901, zone_id="R-TWIN", name="Twin")
    detector = NoFlyZoneDetector(live.cfg, [p901, twin], emit_open=True)
    detections = detector.detect_observations([inside(0)])
    assert sorted(d.metadata["extras"]["zone_id"] for d in detections) == ["P-901", "R-TWIN"]
    assert len({detection_dedup_key(d) for d in detections}) == 2


def test_aircraft_is_the_first_entity_and_the_zone_follows(live: NoFlyZoneDetector) -> None:
    """entities_involved[0] is the aircraft: the dashboard and entity_id column read it."""
    [entry] = live.detect_observations([inside(0)])
    aircraft, zone = entry.entities_involved
    assert (aircraft.entity_id, aircraft.entity_type) == ("aircraft:a1b2c3", "aircraft")
    assert (zone.entity_id, zone.entity_type, zone.domain) == ("zone:P-901", "airspace_zone", "air")


def test_an_empty_window_emits_nothing(live: NoFlyZoneDetector) -> None:
    live.detect_observations([inside(0)])
    assert live.detect_observations([]) == []


def test_flush_still_closes_what_is_open(live: NoFlyZoneDetector) -> None:
    live.detect_observations([inside(0)])
    live.detect_observations([inside(5)])
    [final] = live.flush()
    assert final.metadata["extras"]["episode_status"] == "CLOSED"
    assert final.metadata["extras"]["report_count"] == 2
    assert final.temporal_bounds.end_time == _TS + timedelta(seconds=5)
    assert live.open_episodes == 0


def test_overlapping_windows_still_count_each_report_once(live: NoFlyZoneDetector) -> None:
    live.detect_observations([inside(0), inside(5)])
    [snapshot] = live.detect_observations([inside(0), inside(5), inside(10)])
    assert snapshot.metadata["extras"]["report_count"] == 3
    assert live.skipped_reports == 2


def test_default_detector_still_holds_open_episodes() -> None:
    detector = build_detector()
    assert detector.detect_observations([inside(0)]) == []
    [closed] = detector.detect_observations([outside(1), outside(2)])
    assert closed.metadata["extras"]["episode_status"] == "CLOSED"


def test_live_runner_builds_the_live_detector(monkeypatch: pytest.MonkeyPatch) -> None:
    path = REPO_ROOT / "scripts" / "run_live_detector.py"
    spec = importlib.util.spec_from_file_location("run_live_detector", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # The script defines a dataclass, which looks its module up in sys.modules.
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    runner = module.RUNNERS["no_fly_zone"]
    assert runner.factory == "build_live_detector"
    assert module.build_detector(runner).emit_open is True
