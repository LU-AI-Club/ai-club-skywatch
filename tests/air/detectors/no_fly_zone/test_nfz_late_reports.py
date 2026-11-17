"""Late reports must not split one incursion into two rows.

The live feed hands back each aircraft's latest position, often well behind
other aircraft's. Silence closes an episode, and it is measured against the
newest report from anyone. Without slack, an aircraft whose reports arrive
behind the rest is closed while they are still coming, and the next batch opens
a second episode for the same incursion with a new start time.
``sampling.feed_lateness_sec`` holds the silence clock back by that much.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from nfz_support import FIXTURES  # noqa: E402

from air.detectors.no_fly_zone import build_detector, build_live_detector  # noqa: E402
from air.detectors.no_fly_zone.adapter import NoFlyZoneDetector  # noqa: E402
from air.detectors.no_fly_zone.config import Config, _validate, load_config  # noqa: E402
from air.detectors.no_fly_zone.ingest.airspace_loader import load_filtered_zones  # noqa: E402
from air.models.observation import AdsbObservation  # noqa: E402

FIXTURE_ZONES = FIXTURES / "airspace" / "klyh-150nm.geojson"
T0 = datetime(2026, 9, 22, 20, 15, tzinfo=UTC)


def _obs(icao24: str, seconds: int, *, inside: bool) -> AdsbObservation:
    """``inside`` puts it in fixture zone P-901, below its ceiling."""
    lat, lon = (37.425, -79.215) if inside else (36.0, -81.0)
    return AdsbObservation(
        icao24=icao24,
        observed_at=T0 + timedelta(seconds=seconds),
        latitude=lat,
        longitude=lon,
        altitude_ft=4850.0,
        alt_geom_ft=5200.0,
        ground_speed_kt=180.0,
        track_deg=0.0,
        callsign="TEST123",
        squawk="1200",
        emitter_category="A3",
        nic=8,
        nacp=9,
        on_ground=False,
        source_row_id=f"{icao24}:{seconds}",
    )


def _cfg(lateness_sec: float | None) -> Config:
    raw = dict(load_config().raw)
    sampling = dict(raw["sampling"])
    sampling.pop("feed_lateness_sec", None)
    if lateness_sec is not None:
        sampling["feed_lateness_sec"] = lateness_sec
    raw["sampling"] = sampling
    return Config(raw)


def _late_delivery(detector: NoFlyZoneDetector) -> list[Any]:
    """Aircraft A loiters in P-901 from t=0 to t=155 s, reporting every 5 s.

    Its reports reach the detector about a minute behind aircraft B's:
      window 1 - A 0..95,     B 0..95
      window 2 -              B 100..155   (A's next reports are still in transit)
      window 3 - A 100..155,  B 160
    Then A leaves the zone.
    """
    out: list[Any] = []
    out += detector.detect_observations(
        [_obs("aaaaaa", s, inside=True) for s in range(0, 100, 5)]
        + [_obs("bbbbbb", s, inside=False) for s in range(0, 100, 5)]
    )
    out += detector.detect_observations(
        [_obs("bbbbbb", s, inside=False) for s in range(100, 160, 5)]
    )
    out += detector.detect_observations(
        [_obs("aaaaaa", s, inside=True) for s in range(100, 160, 5)]
        + [_obs("bbbbbb", 160, inside=False)]
    )
    out += detector.detect_observations(
        [_obs("aaaaaa", s, inside=False) for s in (160, 165)]
    )
    out += detector.flush()
    return out


def _episodes(detections: list[Any]) -> set[tuple[datetime, Any]]:
    """(episode_start, status) for each distinct row the store would hold."""
    rows = {}
    for d in detections:
        extras = d.metadata["extras"]
        rows[extras["episode_start"]] = extras.get("episode_end")
    return set(rows.items())


def test_late_reports_extend_the_incursion_instead_of_starting_a_second() -> None:
    detector = build_detector(airspace_path=FIXTURE_ZONES)
    rows = _episodes(_late_delivery(detector))
    assert rows == {(T0, T0 + timedelta(seconds=155))}


def test_live_mode_keeps_one_row_for_the_incursion() -> None:
    """Live mode upserts on the episode's start, so one start means one row."""
    detector = build_live_detector(airspace_path=FIXTURE_ZONES)
    starts = {d.metadata["extras"]["episode_start"] for d in _late_delivery(detector)}
    assert starts == {T0}


def test_without_lateness_the_same_feed_splits_the_incursion() -> None:
    """Pins the bug the setting fixes, so removing it shows up here."""
    cfg = _cfg(0)
    detector = NoFlyZoneDetector(cfg, load_filtered_zones(FIXTURE_ZONES, cfg))
    starts = {d.metadata["extras"]["episode_start"] for d in _late_delivery(detector)}
    assert starts == {T0, T0 + timedelta(seconds=100)}


def test_a_truly_silent_aircraft_still_closes_once_past_the_lateness() -> None:
    """Holding the clock back delays closing; it does not stop it."""
    detector = build_detector(airspace_path=FIXTURE_ZONES)
    lateness = float(load_config()["sampling"]["feed_lateness_sec"])
    gap = float(load_config()["sampling"]["max_gap_sec"])
    detector.detect_observations([_obs("aaaaaa", s, inside=True) for s in range(0, 30, 5)])
    quiet_until = int(25 + gap + lateness)
    assert detector.detect_observations([_obs("bbbbbb", quiet_until, inside=False)]) == []
    closed = detector.detect_observations([_obs("bbbbbb", quiet_until + 1, inside=False)])
    assert [d.metadata["extras"]["episode_start"] for d in closed] == [T0]


@pytest.mark.parametrize(
    "sampling",
    [{"feed_lateness_sec": -1}, {"feed_lateness_sec": 3600}],
)
def test_config_rejects_a_bad_lateness(sampling: dict[str, float]) -> None:
    raw = dict(load_config().raw)
    raw["sampling"] = {**raw["sampling"], **sampling}
    with pytest.raises(ValueError, match="feed_lateness_sec"):
        _validate(raw)
