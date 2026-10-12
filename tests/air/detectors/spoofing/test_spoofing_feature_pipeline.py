"""Tests for the feature stage beyond haversine_m.

Covers heading_delta_deg, group_by_aircraft, split_segments,
build_pair_features and build_features.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.features import (
    build_features,
    build_pair_features,
    group_by_aircraft,
    heading_delta_deg,
    split_segments,
)
from air.models.observation import AdsbObservation

T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def obs(
    seconds: float = 0.0,
    icao24: str = "a1b2c3",
    lat: float = 37.0,
    lon: float = -79.0,
    **kwargs,
) -> AdsbObservation:
    return AdsbObservation(
        icao24=icao24,
        observed_at=T0 + timedelta(seconds=seconds),
        latitude=lat,
        longitude=lon,
        **kwargs,
    )


# --- heading_delta_deg -------------------------------------------------------
@pytest.mark.parametrize(
    "a, b, expected",
    [
        (0.0, 10.0, 10.0),      # simple right turn
        (10.0, 0.0, -10.0),     # simple left turn
        (359.0, 1.0, 2.0),      # wraps forward through north
        (1.0, 359.0, -2.0),     # wraps backward through north
        (90.0, 90.0, 0.0),      # no turn
        (0.0, 180.0, -180.0),   # an exact reversal lands on the -180 edge
    ],
)
def test_heading_delta_handles_the_wrap(a, b, expected):
    """359 to 1 is a 2 degree turn, not -358."""
    assert heading_delta_deg(a, b) == pytest.approx(expected)


# --- group_by_aircraft -------------------------------------------------------
def test_mixed_stream_splits_into_one_track_per_aircraft():
    stream = [obs(0, "aaa"), obs(1, "bbb"), obs(2, "aaa")]
    tracks = group_by_aircraft(stream)
    assert set(tracks) == {"aaa", "bbb"}
    assert len(tracks["aaa"]) == 2


def test_each_track_comes_back_in_time_order():
    """Messages do arrive out of order; arrival order would invent movement."""
    tracks = group_by_aircraft([obs(30), obs(0), obs(15)])
    times = [o.observed_at for o in tracks["a1b2c3"]]
    assert times == sorted(times)


def test_no_observations_gives_no_tracks():
    assert group_by_aircraft([]) == {}


# --- split_segments ----------------------------------------------------------
def test_a_steady_track_stays_one_segment():
    track = [obs(i * 5) for i in range(6)]
    assert len(split_segments(track, max_gap_s=60.0)) == 1


def test_a_long_silence_starts_a_new_segment():
    track = [obs(0), obs(5), obs(600), obs(605)]
    segments = split_segments(track, max_gap_s=60.0)
    assert [len(s) for s in segments] == [2, 2]


def test_a_gap_exactly_at_the_limit_does_not_split():
    """The rule is "longer than", so 60 s with a 60 s limit stays together."""
    assert len(split_segments([obs(0), obs(60)], max_gap_s=60.0)) == 1


def test_an_empty_track_gives_no_segments():
    assert split_segments([], max_gap_s=60.0) == []


# --- build_pair_features -----------------------------------------------------
def test_a_pair_yields_the_arithmetic():
    """One degree of latitude is about 111,195 m; over 60 s that is ~3,601 kt."""
    record = build_pair_features(obs(0, lat=37.0), obs(60, lat=38.0))
    assert record is not None
    assert record.dt_s == 60.0
    assert record.dist_m == pytest.approx(111_195, rel=0.001)
    assert record.implied_speed_kt == pytest.approx(3_601, rel=0.01)


def test_claimed_and_derived_speed_are_both_kept():
    record = build_pair_features(
        obs(0, lat=37.0), obs(60, lat=38.0, ground_speed_kt=450.0)
    )
    assert record is not None
    assert record.reported_speed_kt == 450.0
    assert record.speed_delta_kt == pytest.approx(
        record.implied_speed_kt - 450.0
    )


def test_climb_rate_comes_from_the_altitudes():
    record = build_pair_features(
        obs(0, altitude_ft=10_000.0),
        obs(60, altitude_ft=12_000.0, vertical_rate_fpm=2_000.0),
    )
    assert record is not None
    assert record.implied_vrate_fpm == pytest.approx(2_000.0)
    assert record.vrate_delta_fpm == pytest.approx(0.0)


def test_turn_rate_is_signed_and_wrapped():
    record = build_pair_features(
        obs(0, track_deg=359.0), obs(10, track_deg=1.0)
    )
    assert record is not None
    assert record.turn_rate_dps == pytest.approx(0.2)


def test_a_non_positive_time_gap_is_dropped():
    """Out-of-order arrivals would otherwise imply infinite speed."""
    assert build_pair_features(obs(10), obs(10)) is None
    assert build_pair_features(obs(10), obs(0)) is None


def test_two_different_aircraft_are_never_paired():
    assert build_pair_features(obs(0, "aaa"), obs(5, "bbb")) is None


def test_missing_optional_fields_stay_none():
    """Not reported is not zero, and a rule must abstain on it."""
    record = build_pair_features(obs(0), obs(10))
    assert record is not None
    assert record.reported_speed_kt is None
    assert record.speed_delta_kt is None
    assert record.turn_rate_dps is None


# --- build_features ----------------------------------------------------------
def test_one_record_per_consecutive_pair():
    records = build_features([obs(0), obs(5), obs(10)])
    assert len(records) == 2


def test_no_record_spans_a_gap():
    """Four points with a ten-minute hole give 1 pair, not 3."""
    records = build_features([obs(0), obs(5), obs(600), obs(605)], max_gap_s=60.0)
    assert len(records) == 2
    assert {r.segment_id for r in records} == {0, 1}


def test_every_aircraft_is_covered():
    records = build_features(
        [obs(0, "aaa"), obs(5, "aaa"), obs(0, "bbb"), obs(5, "bbb")]
    )
    assert {r.icao24 for r in records} == {"aaa", "bbb"}


def test_a_single_report_produces_nothing():
    """One observation has nothing to contradict it."""
    assert build_features([obs(0)]) == []


def test_runs_over_a_real_fixture(observations_from):
    records = build_features(observations_from("spoofing/clean_track.json"))
    assert len(records) == 39          # 40 points, one unbroken segment
    assert all(r.segment_id == 0 for r in records)
    assert all(r.implied_speed_kt == pytest.approx(450.0, rel=0.02) for r in records)
