"""Threshold table + gates. OWNER: CalebK.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_rules.py -q -rxX
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from air.detectors.proximity import PairGeometry, flag_pair, load_config, severity_for
from air.models.observation import AdsbObservation
from contracts import SeverityLevel
from tests.air.detectors.proximity._todo import todo

CFG = load_config()
T0 = datetime(2026, 9, 1, 0, 30, 0, tzinfo=timezone.utc)
_A = AdsbObservation(icao24="aaa001", observed_at=T0, latitude=37.4, longitude=-79.1, altitude_ft=10000.0)
_B = AdsbObservation(icao24="bbb002", observed_at=T0, latitude=37.4, longitude=-79.0, altitude_ft=10200.0)


def _geom(t_cpa, pred_h, pred_v, now_nm=5.0):
    """A PairGeometry with only the fields the rules care about filled in."""
    return PairGeometry(
        icao_a="aaa001", icao_b="bbb002", at=T0,
        horizontal_now_nm=now_nm, vertical_now_ft=200.0, closure_rate_kt=600.0,
        t_cpa_s=t_cpa, predicted_horizontal_nm=pred_h, predicted_vertical_ft=pred_v,
        obs_a=_A, obs_b=_B,
    )


# --- severity_for: the table ------------------------------------------------------

@pytest.mark.parametrize(
    "h_nm, v_ft, expected",
    [
        (0.2, 200, SeverityLevel.HIGH),
        (0.49, 399, SeverityLevel.HIGH),
        (0.5, 200, SeverityLevel.MEDIUM),     # on the HIGH boundary -> next tier
        (0.2, 400, SeverityLevel.MEDIUM),     # vertical alone can push it down a tier
        (1.4, 699, SeverityLevel.MEDIUM),
        (1.5, 200, SeverityLevel.LOW),
        (2.9, 899, SeverityLevel.LOW),   # LOW is now the loosest tier
        (2.9, 900, None),                     # ~standard 1000 ft separation, not an event
        (3.0, 200, None),   # PROX-3: was INFO, now below the emit floor
        (4.9, 899, None),   # PROX-3: lawfully separated, not emitted
        (4.9, 975, None),                     # 1000 ft standard, jittered low by altimetry
        (5.0, 200, None),                     # outside every tier
        (0.2, 1000, None),                    # close laterally, legally separated vertically
        (0.2, 2000, None),
    ],
)
def test_severity_table(h_nm, v_ft, expected):
    assert severity_for(h_nm, v_ft, CFG) is expected


def test_both_limits_must_hold():
    # 0.1 nm horizontal would be HIGH, but 800 ft vertical is only LOW-grade.
    assert severity_for(0.1, 800, CFG) is SeverityLevel.LOW


def test_severity_reads_config_not_constants():
    from air.detectors.proximity import ProximityConfig, SeverityTier

    strict = ProximityConfig(tiers=(SeverityTier("HIGH", 10.0, 5000.0),))
    assert severity_for(4.0, 3000, strict) is SeverityLevel.HIGH


# --- flag_pair: the gates -----------------------------------------------------------
def test_flag_converging_inside_window_fires():
    assert flag_pair(_geom(60.0, 0.2, 200.0), CFG) is SeverityLevel.HIGH


def test_flag_diverging_is_suppressed():
    assert flag_pair(_geom(-60.0, 0.2, 200.0), CFG) is None


def test_flag_too_far_in_future_is_suppressed():
    assert flag_pair(_geom(CFG.max_tcpa_s + 1, 0.2, 200.0), CFG) is None
    assert flag_pair(_geom(CFG.max_tcpa_s, 0.2, 200.0), CFG) is SeverityLevel.HIGH


def test_flag_no_relative_motion_is_suppressed():
    assert flag_pair(_geom(None, None, None), CFG) is None


def test_flag_outside_all_tiers_is_none():
    assert flag_pair(_geom(60.0, 6.0, 200.0), CFG) is None


# --- flag_pair: don't trust a prediction from a pair that is already far apart (PROX-1) ---
def test_flag_far_apart_now_is_suppressed():
    far = CFG.max_current_separation_nm + 0.1
    assert flag_pair(_geom(60.0, 0.2, 200.0, now_nm=far), CFG) is None
    assert flag_pair(_geom(60.0, 0.2, 200.0, now_nm=31.8), CFG) is None


def test_flag_current_separation_boundary_is_inclusive():
    on_limit = CFG.max_current_separation_nm
    assert flag_pair(_geom(60.0, 0.2, 200.0, now_nm=on_limit), CFG) is SeverityLevel.HIGH


# --- PROX-8: terminal-airspace altitude floor -----------------------------------
def _geom_at(alt_a, alt_b, t_cpa=60.0, pred_h=0.2, pred_v=200.0, now_nm=5.0):
    """A PairGeometry that would fire, at a chosen pair of altitudes."""
    a = AdsbObservation(icao24="aaa001", observed_at=T0, latitude=37.4, longitude=-79.1,
                        altitude_ft=alt_a, ground_speed_kt=300.0, track_deg=90.0)
    b = AdsbObservation(icao24="bbb002", observed_at=T0, latitude=37.4, longitude=-79.0,
                        altitude_ft=alt_b, ground_speed_kt=300.0, track_deg=270.0)
    return PairGeometry(
        icao_a="aaa001", icao_b="bbb002", at=T0,
        horizontal_now_nm=now_nm,
        vertical_now_ft=abs(alt_b - alt_a) if None not in (alt_a, alt_b) else 0.0,
        closure_rate_kt=600.0,
        t_cpa_s=t_cpa, predicted_horizontal_nm=pred_h, predicted_vertical_ft=pred_v,
        obs_a=a, obs_b=b,
    )


def test_pair_above_the_floor_still_fires():
    assert flag_pair(_geom_at(10000.0, 10200.0), CFG) is SeverityLevel.HIGH


def test_pair_below_the_floor_is_suppressed():
    assert flag_pair(_geom_at(3000.0, 3200.0), CFG) is None


def test_one_aircraft_below_the_floor_suppresses_the_pair():
    # The lower aircraft is the one in terminal airspace; that is enough.
    assert flag_pair(_geom_at(4999.0, 12000.0), CFG) is None


def test_floor_boundary_is_inclusive():
    floor = CFG.min_altitude_ft
    assert flag_pair(_geom_at(floor, floor + 200), CFG) is SeverityLevel.HIGH
    assert flag_pair(_geom_at(floor - 1, floor + 200), CFG) is None


def test_missing_altitude_abstains():
    assert flag_pair(_geom_at(None, 12000.0), CFG) is None


def test_floor_reads_config_not_a_constant():
    from dataclasses import replace as _replace

    ground_level = _replace(CFG, min_altitude_ft=0.0)
    assert flag_pair(_geom_at(3000.0, 3200.0), ground_level) is SeverityLevel.HIGH


def test_fixture_generator_still_runs():
    """PROX-8: the generator lost a brace in a merge and nobody noticed, because
    the fixtures it writes were already committed. Import-compile it so a future
    merge can't break it silently."""
    import py_compile
    from pathlib import Path

    py_compile.compile(
        str(Path(__file__).resolve().parents[4] / "scripts" / "make_proximity_fixtures.py"),
        doraise=True,
    )
