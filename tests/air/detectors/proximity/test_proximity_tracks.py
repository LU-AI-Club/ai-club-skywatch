"""Time alignment. OWNER: Erik.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_tracks.py -q -rxX
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.proximity import load_config
from air.detectors.proximity.tracks import align_tracks, group_tracks, interpolate_to_grid
from air.models.observation import AdsbObservation
from tests.air.detectors.proximity._todo import todo
from tests.conftest import load_observations

T0 = datetime(2026, 9, 1, 0, 30, 0, tzinfo=timezone.utc)


def _obs(seconds, lat=37.0, lon=-79.0, alt=10000.0, gs=300.0, track=90.0, icao="aaa001"):
    return AdsbObservation(
        icao24=icao,
        observed_at=T0 + timedelta(seconds=seconds),
        latitude=lat,
        longitude=lon,
        altitude_ft=alt,
        ground_speed_kt=gs,
        track_deg=track,
        vertical_rate_fpm=0.0,
    )


# --- group_tracks: done ---------------------------------------------------------
def test_group_tracks_sorts_each_aircraft_by_time():
    obs = [_obs(5), _obs(1, icao="bbb002"), _obs(0), _obs(3, icao="bbb002")]
    tracks = group_tracks(obs)
    assert set(tracks) == {"aaa001", "bbb002"}
    assert [o.observed_at for o in tracks["aaa001"]] == [T0, T0 + timedelta(seconds=5)]


# --- interpolate_to_grid --------------------------------------------------------
@todo("Erik")
def test_grid_ticks_are_whole_seconds():
    out = interpolate_to_grid([_obs(0.4), _obs(4.6)], step_s=1.0)
    assert [o.observed_at for o in out] == [T0 + timedelta(seconds=s) for s in (1, 2, 3, 4)]


@todo("Erik")
def test_position_is_blended_linearly():
    out = interpolate_to_grid([_obs(0.0, lat=37.0, alt=10000.0), _obs(10.0, lat=37.1, alt=11000.0)])
    at_5 = next(o for o in out if o.observed_at == T0 + timedelta(seconds=5))
    assert at_5.latitude == pytest.approx(37.05)
    assert at_5.altitude_ft == pytest.approx(10500.0)


@todo("Erik")
def test_tick_on_a_real_report_returns_that_report():
    out = interpolate_to_grid([_obs(0.0, lat=37.0), _obs(2.0, lat=37.2)])
    assert out[0].observed_at == T0
    assert out[0].latitude == pytest.approx(37.0)


@todo("Erik")
def test_track_angle_wraps_the_short_way():
    # 350 -> 10 passes through 0 (north), not through 180 (south).
    out = interpolate_to_grid([_obs(0.0, track=350.0), _obs(2.0, track=10.0)])
    at_1 = next(o for o in out if o.observed_at == T0 + timedelta(seconds=1))
    assert at_1.track_deg == pytest.approx(0.0, abs=1e-6)


@todo("Erik")
def test_no_interpolation_across_a_long_silence():
    out = interpolate_to_grid([_obs(0.0), _obs(2.0), _obs(100.0), _obs(102.0)], max_gap_s=30.0)
    seconds = sorted((o.observed_at - T0).total_seconds() for o in out)
    assert seconds == [0, 1, 2, 100, 101, 102]


@todo("Erik")
def test_other_fields_copied_from_before_point():
    out = interpolate_to_grid([_obs(0.0), _obs(4.0)])
    assert all(o.icao24 == "aaa001" for o in out)
    assert all(o.ground_speed_kt == pytest.approx(300.0) for o in out)


@todo("Erik")
def test_single_point_track_yields_nothing():
    assert interpolate_to_grid([_obs(0.0)]) == []
    assert interpolate_to_grid([]) == []


# --- align_tracks: done, but depends on interpolate_to_grid ---------------------
@todo("Erik")
def test_align_tracks_puts_both_aircraft_on_the_same_ticks():
    cfg = load_config()
    snapshots = align_tracks(load_observations("proximity_head_on.json"), cfg)
    # The fixture's two aircraft NEVER report at the same instant, yet after
    # alignment every tick from 2 s to 19 s holds one point for each of them.
    both = [t for t, snap in snapshots.items() if {o.icao24 for o in snap} == {"aaa001", "bbb002"}]
    assert len(both) >= 17
    assert all(t.microsecond == 0 for t in snapshots)
