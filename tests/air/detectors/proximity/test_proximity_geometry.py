"""Geometry primitives. OWNER: Manni.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_geometry.py -q -rxX
"""

from __future__ import annotations

import math

import pytest

from air.detectors.proximity.geometry import (
    M_PER_NM,
    haversine_nm,
    predicted_separation,
    time_to_cpa,
    to_local_xy,
    velocity_xy,
)
from tests.air.detectors.proximity._todo import todo

LYH = (37.4138, -79.1422)


# --- haversine_nm: already done, here as the model ----------------------------
def test_haversine_zero_for_same_point():
    assert haversine_nm(*LYH, *LYH) == 0.0


def test_haversine_one_degree_of_latitude_is_sixty_nm():
    # By definition: 1 nautical mile = 1 minute of latitude.
    assert haversine_nm(37.0, -79.0, 38.0, -79.0) == pytest.approx(60.0, rel=0.01)


# --- to_local_xy ----------------------------------------------------------------
@todo("Manni")
def test_local_xy_of_reference_is_origin():
    assert to_local_xy(*LYH, *LYH) == (0.0, 0.0)


@todo("Manni")
def test_local_xy_north_is_positive_y():
    x, y = to_local_xy(LYH[0] + 1 / 60, LYH[1], *LYH)  # one minute north = 1 nm
    assert x == pytest.approx(0.0, abs=1.0)
    assert y == pytest.approx(M_PER_NM, rel=0.01)


@todo("Manni")
def test_local_xy_east_shrinks_with_latitude():
    # One degree of longitude at 37.4 N is cos(37.4 deg) of a degree at the equator.
    x, _ = to_local_xy(LYH[0], LYH[1] + 1.0, *LYH)
    x_equator, _ = to_local_xy(0.0, 1.0, 0.0, 0.0)
    assert x / x_equator == pytest.approx(math.cos(math.radians(LYH[0])), rel=0.001)


@todo("Manni")
def test_local_xy_agrees_with_haversine_at_short_range():
    lat2, lon2 = LYH[0] + 0.1, LYH[1] + 0.1
    x, y = to_local_xy(lat2, lon2, *LYH)
    assert math.hypot(x, y) / M_PER_NM == pytest.approx(haversine_nm(*LYH, lat2, lon2), rel=0.005)


# --- velocity_xy ----------------------------------------------------------------
@todo("Manni")
def test_velocity_north_track():
    vx, vy = velocity_xy(360.0, 0.0)  # 360 kt due north = 0.1 nm/s = 185.2 m/s
    assert vx == pytest.approx(0.0, abs=1e-6)
    assert vy == pytest.approx(185.2)


@todo("Manni")
def test_velocity_east_track_is_positive_x():
    vx, vy = velocity_xy(100.0, 90.0)
    assert vx > 0 and vy == pytest.approx(0.0, abs=1e-6)


@todo("Manni")
def test_velocity_southwest():
    vx, vy = velocity_xy(100.0, 225.0)
    assert vx < 0 and vy < 0 and vx == pytest.approx(vy)


# --- time_to_cpa ----------------------------------------------------------------
@todo("Manni")
def test_tcpa_head_on():
    # B is 6000 m east of A and closing at 100 m/s -> closest in 60 s.
    assert time_to_cpa(6000.0, 0.0, -100.0, 0.0) == pytest.approx(60.0)


@todo("Manni")
def test_tcpa_negative_when_diverging():
    # B is 6000 m east and moving further east: closest approach was in the past.
    assert time_to_cpa(6000.0, 0.0, 100.0, 0.0) == pytest.approx(-60.0)


@todo("Manni")
def test_tcpa_none_when_no_relative_motion():
    assert time_to_cpa(6000.0, 0.0, 0.0, 0.0) is None


@todo("Manni")
def test_tcpa_crossing():
    # B at (1000, 1000) moving (-10, -10): straight at A, |r|/|v| = 100 s.
    assert time_to_cpa(1000.0, 1000.0, -10.0, -10.0) == pytest.approx(100.0)


# --- predicted_separation -------------------------------------------------------
@todo("Manni")
def test_predicted_separation_head_on_hits_zero():
    h, v = predicted_separation(6000.0, 0.0, -100.0, 0.0, 60.0, 0.0, 0.0)
    assert h == pytest.approx(0.0, abs=1e-9)
    assert v == 0.0


@todo("Manni")
def test_predicted_separation_lateral_offset_survives():
    # 370.4 m north offset = 0.2 nm; head-on motion never removes it.
    h, _ = predicted_separation(6000.0, 370.4, -100.0, 0.0, 60.0, 0.0, 0.0)
    assert h == pytest.approx(0.2, rel=1e-6)


@todo("Manni")
def test_predicted_separation_vertical_uses_rate_difference():
    # 1000 ft apart now, B descending 600 fpm faster than A -> 400 ft in 60 s.
    _, v = predicted_separation(0.0, 0.0, 0.0, 0.0, 60.0, 1000.0, -600.0)
    assert v == pytest.approx(400.0)


@todo("Manni")
def test_predicted_separation_is_never_negative():
    _, v = predicted_separation(0.0, 0.0, 0.0, 0.0, 60.0, 200.0, -600.0)
    assert v == pytest.approx(400.0)  # crossed through and out the other side
