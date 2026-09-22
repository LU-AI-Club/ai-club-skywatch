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


def _geom(t_cpa, pred_h, pred_v):
    """A PairGeometry with only the fields the rules care about filled in."""
    return PairGeometry(
        icao_a="aaa001", icao_b="bbb002", at=T0,
        horizontal_now_nm=5.0, vertical_now_ft=200.0, closure_rate_kt=600.0,
        t_cpa_s=t_cpa, predicted_horizontal_nm=pred_h, predicted_vertical_ft=pred_v,
        obs_a=_A, obs_b=_B,
    )


# --- severity_for: the table ------------------------------------------------------
@todo("CalebK")
@pytest.mark.parametrize(
    "h_nm, v_ft, expected",
    [
        (0.2, 200, SeverityLevel.HIGH),
        (0.49, 399, SeverityLevel.HIGH),
        (0.5, 200, SeverityLevel.MEDIUM),     # on the HIGH boundary -> next tier
        (0.2, 400, SeverityLevel.MEDIUM),     # vertical alone can push it down a tier
        (1.4, 699, SeverityLevel.MEDIUM),
        (1.5, 200, SeverityLevel.LOW),
        (2.9, 999, SeverityLevel.LOW),
        (3.0, 200, SeverityLevel.INFO),
        (4.9, 999, SeverityLevel.INFO),
        (5.0, 200, None),                     # outside every tier
        (0.2, 1000, None),                    # close laterally, legally separated vertically
        (0.2, 2000, None),
    ],
)
def test_severity_table(h_nm, v_ft, expected):
    assert severity_for(h_nm, v_ft, CFG) is expected


@todo("CalebK")
def test_both_limits_must_hold():
    # 0.1 nm horizontal would be HIGH, but 800 ft vertical is only LOW-grade.
    assert severity_for(0.1, 800, CFG) is SeverityLevel.LOW


@todo("CalebK")
def test_severity_reads_config_not_constants():
    from air.detectors.proximity import ProximityConfig, SeverityTier

    strict = ProximityConfig(tiers=(SeverityTier("HIGH", 10.0, 5000.0),))
    assert severity_for(4.0, 3000, strict) is SeverityLevel.HIGH


# --- flag_pair: the gates -----------------------------------------------------------
@todo("CalebK")
def test_flag_converging_inside_window_fires():
    assert flag_pair(_geom(60.0, 0.2, 200.0), CFG) is SeverityLevel.HIGH


@todo("CalebK")
def test_flag_diverging_is_suppressed():
    assert flag_pair(_geom(-60.0, 0.2, 200.0), CFG) is None


@todo("CalebK")
def test_flag_too_far_in_future_is_suppressed():
    assert flag_pair(_geom(CFG.max_tcpa_s + 1, 0.2, 200.0), CFG) is None
    assert flag_pair(_geom(CFG.max_tcpa_s, 0.2, 200.0), CFG) is SeverityLevel.HIGH


@todo("CalebK")
def test_flag_no_relative_motion_is_suppressed():
    assert flag_pair(_geom(None, None, None), CFG) is None


@todo("CalebK")
def test_flag_outside_all_tiers_is_none():
    assert flag_pair(_geom(60.0, 6.0, 200.0), CFG) is None
