"""Time alignment. OWNER: Erik.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_tracks.py -q -rxX
"""

from __future__ import annotations

import math
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from air.detectors.proximity import load_config
from air.detectors.proximity.tracks import align_tracks, group_tracks, interpolate_to_grid
from air.models.observation import AdsbObservation
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
def test_grid_ticks_are_whole_seconds():
    out = interpolate_to_grid([_obs(0.4), _obs(4.6)], step_s=1.0)
    assert [o.observed_at for o in out] == [T0 + timedelta(seconds=s) for s in (1, 2, 3, 4)]


def test_position_is_blended_linearly():
    before = replace(_obs(0, lat=37.0, lon=-79.0, alt=10000, gs=300), vertical_rate_fpm=-200)
    after = replace(_obs(10, lat=37.1, lon=-78.8, alt=11000, gs=400), vertical_rate_fpm=600)
    out = interpolate_to_grid([before, after])
    at_5 = next(o for o in out if o.observed_at == T0 + timedelta(seconds=5))
    assert at_5.latitude == pytest.approx(37.05)
    assert at_5.longitude == pytest.approx(-78.9)
    assert at_5.altitude_ft == pytest.approx(10500.0)
    assert at_5.ground_speed_kt == pytest.approx(350.0)
    assert at_5.vertical_rate_fpm == pytest.approx(200.0)


def test_tick_on_a_real_report_returns_that_report():
    out = interpolate_to_grid([_obs(0.0, lat=37.0), _obs(2.0, lat=37.2)])
    assert out[0].observed_at == T0
    assert out[0].latitude == pytest.approx(37.0)


@pytest.mark.parametrize("before_angle, after_angle", [(350.0, 10.0), (10.0, 350.0)])
def test_track_angle_wraps_the_short_way(before_angle, after_angle):
    # Both directions pass through 0 (north), not through 180 (south).
    out = interpolate_to_grid([_obs(0.0, track=before_angle), _obs(2.0, track=after_angle)])
    at_1 = next(o for o in out if o.observed_at == T0 + timedelta(seconds=1))
    assert at_1.track_deg == pytest.approx(0.0, abs=1e-6)


def test_no_interpolation_across_a_long_silence():
    out = interpolate_to_grid([_obs(0.0), _obs(2.0), _obs(100.0), _obs(102.0)], max_gap_s=30.0)
    seconds = sorted((o.observed_at - T0).total_seconds() for o in out)
    assert seconds == [0, 1, 2, 100, 101, 102]


def test_other_fields_copied_from_before_point():
    out = interpolate_to_grid([_obs(0.0), _obs(4.0)])
    assert all(o.icao24 == "aaa001" for o in out)
    assert all(o.ground_speed_kt == pytest.approx(300.0) for o in out)


def test_single_point_track_yields_nothing():
    assert interpolate_to_grid([_obs(0.0)]) == []
    assert interpolate_to_grid([]) == []


def _ticks(out):
    return [(o.observed_at - T0).total_seconds() for o in out]


def test_exact_hit_keeps_that_reports_metadata():
    old = replace(_obs(0.0), callsign="OLD", squawk="1200", nic=7, nacp=8, receiver_id="r1")
    new = replace(_obs(2.0), callsign="NEW", squawk="7700", nic=9, nacp=10, receiver_id="r2")
    out = interpolate_to_grid([old, new])
    assert out[0] == old
    assert out[1].callsign == "OLD"  # in between: copied from `before`
    assert out[2] == new


def test_exact_hit_keeps_values_missing_at_the_other_end():
    known = _obs(0.0, alt=10000.0, track=90.0)
    blank = replace(_obs(2.0), altitude_ft=None, track_deg=None)
    out = interpolate_to_grid([known, blank])
    assert (out[0].altitude_ft, out[0].track_deg) == (10000.0, 90.0)
    assert (out[1].altitude_ft, out[1].track_deg) == (None, None)  # abstain, don't guess

    out = interpolate_to_grid([blank, replace(known, observed_at=T0 + timedelta(seconds=4))])
    assert (out[-1].altitude_ft, out[-1].track_deg) == (10000.0, 90.0)


def test_interior_exact_hit_keeps_that_reports_values_and_metadata():
    a = replace(_obs(0, alt=10000), callsign="A")
    b = replace(_obs(2, alt=11000), callsign="B", nic=9, receiver_id="r2")
    c = replace(_obs(4, alt=12000), callsign="C")
    out = interpolate_to_grid([a, b, c])
    assert _ticks(out) == [0, 1, 2, 3, 4]
    assert out[2] == b
    assert out[1].callsign == "A"
    assert out[3].callsign == "B"


def test_interpolation_preserves_input_and_is_repeatable():
    track = [_obs(0, alt=10000), _obs(2, alt=11000), _obs(4, alt=12000)]
    snapshot = deepcopy(track)
    original_elements = tuple(track)
    first = interpolate_to_grid(track)
    second = interpolate_to_grid(track)
    assert track == snapshot
    assert len(track) == len(original_elements)
    assert all(current is original for current, original in zip(track, original_elements))
    assert first is not track and second is not track
    assert first == second


def test_ten_year_gap_with_microsecond_grid_stays_fast():
    # A subprocess timeout prevents a per-tick regression from hanging pytest.
    result = subprocess.run(
        [sys.executable, "-c", """
from dataclasses import replace
from air.detectors.proximity.tracks import interpolate_to_grid
from tests.air.detectors.proximity.test_proximity_tracks import _obs, T0
before = _obs(0)
after = replace(before, observed_at=T0.replace(year=T0.year + 10))
assert interpolate_to_grid([before, after], step_s=1e-6) == [before, after]
"""],
        cwd=Path(__file__).resolve().parents[4],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


def test_reports_surrounded_by_long_gaps_are_kept_but_not_blended():
    assert _ticks(interpolate_to_grid([_obs(0.0), _obs(100.0), _obs(200.0)])) == [0, 100, 200]
    out = interpolate_to_grid([_obs(0.0), _obs(2.0), _obs(100.0), _obs(200.0), _obs(202.0)])
    assert _ticks(out) == [0, 1, 2, 100, 200, 201, 202]


def test_off_grid_report_between_long_gaps_yields_nothing():
    assert interpolate_to_grid([_obs(0.5), _obs(100.5)]) == []


def test_duplicate_timestamps_emit_one_tick_first_report_wins():
    a = replace(_obs(0.0), callsign="A")
    b = replace(_obs(0.0), callsign="B")
    assert interpolate_to_grid([a, b]) == [a]

    out = interpolate_to_grid([a, b, _obs(2.0)])
    assert _ticks(out) == [0, 1, 2]
    assert out[0] == a


def test_gap_threshold_is_not_rounded():
    out = interpolate_to_grid([_obs(0.0), _obs(2.0)], max_gap_s=1.9999996)
    assert _ticks(out) == [0, 2]
    out = interpolate_to_grid([_obs(0.0), _obs(30.0)], max_gap_s=30.0)
    assert len(out) == 31  # exactly max_gap_s is still allowed


def test_non_integer_step():
    out = interpolate_to_grid([_obs(0.2), _obs(2.2)], step_s=0.5)
    assert _ticks(out) == [0.5, 1.0, 1.5, 2.0]


@pytest.mark.parametrize(
    "gap_s, step_s, expected",
    [
        (1.001, 0.25, [0, 0.25, 0.5, 0.75, 1]),
        (1.000001, 0.25, [0, 0.25, 0.5, 0.75, 1]),
        (0.000249, 0.0001, [0, 0.0001, 0.0002]),
    ],
)
def test_fractional_gap_at_threshold_is_blended(gap_s, step_s, expected):
    out = interpolate_to_grid([_obs(0), _obs(gap_s)], step_s=step_s, max_gap_s=gap_s)
    assert _ticks(out) == expected


def test_gap_above_threshold_by_one_float_step_is_not_blended():
    out = interpolate_to_grid(
        [_obs(0), _obs(1.001)],
        step_s=0.25,
        max_gap_s=math.nextafter(1.001, -math.inf),
    )
    assert _ticks(out) == [0]


def test_sub_microsecond_step_is_rejected():
    # datetime resolves only whole microseconds, so this grid cannot exist.
    with pytest.raises(ValueError):
        interpolate_to_grid([_obs(0.0), _obs(1.0)], step_s=0.0000015)
    with pytest.raises(ValueError):
        interpolate_to_grid([_obs(0.0), _obs(1.0)], step_s=0.0)


@pytest.mark.parametrize("report_count", [0, 1, 2])
@pytest.mark.parametrize("step_s", [math.nan, math.inf, 1e303, 0])
def test_invalid_step_is_rejected_with_clear_message(step_s, report_count):
    with pytest.raises(ValueError) as exc:
        interpolate_to_grid([_obs(0), _obs(2)][:report_count], step_s=step_s)
    assert str(exc.value) == (
        f"step_s must be a positive whole number of microseconds, got {step_s!r}"
    )


@pytest.mark.parametrize("report_count", [0, 1, 2])
@pytest.mark.parametrize("max_gap_s", [math.nan, -1.0])
def test_invalid_max_gap_is_rejected(max_gap_s, report_count):
    with pytest.raises(ValueError, match="max_gap_s must be non-negative and not NaN"):
        interpolate_to_grid([_obs(0), _obs(2)][:report_count], max_gap_s=max_gap_s)


@pytest.mark.parametrize("max_gap_s, expected", [(0, [0, 2]), (math.inf, [0, 1, 2])])
def test_zero_and_infinite_max_gap_remain_valid(max_gap_s, expected):
    assert _ticks(interpolate_to_grid([_obs(0), _obs(2)], max_gap_s=max_gap_s)) == expected


# --- align_tracks: done, but depends on interpolate_to_grid ---------------------
def test_align_tracks_puts_both_aircraft_on_the_same_ticks():
    cfg = load_config()
    snapshots = align_tracks(load_observations("proximity_head_on.json"), cfg)
    # The fixture's two aircraft NEVER report at the same instant, yet after
    # alignment every tick from 2 s to 19 s holds one point for each of them.
    both = [t for t, snap in snapshots.items() if {o.icao24 for o in snap} == {"aaa001", "bbb002"}]
    assert len(both) >= 17
    assert all(t.microsecond == 0 for t in snapshots)
