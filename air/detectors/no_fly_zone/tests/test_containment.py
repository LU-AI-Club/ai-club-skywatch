"""Stream C tests - geo/zone_index.py + geo/containment.py.

Firing case, non-firing case, and two edge cases: a plane just outside the
fence with poor position accuracy, and an empty zone list.
"""
from __future__ import annotations

import pytest
from shapely.geometry import box

from ..config import load_config
from ..geo.containment import check_containment
from ..types import Activation, AirspaceZone, Datum, ExitReason, ZoneType
from .conftest import make_state


def make_p901() -> AirspaceZone:
    """Fixture zone P-901: PROHIBITED, SFC-18000 MSL, always active."""
    return AirspaceZone(
        zone_id="P-901",
        name="Hand-built prohibited area (test)",
        zone_type=ZoneType.PROHIBITED,
        geometry=box(-79.25, 37.40, -79.18, 37.45),
        floor_ft=0.0,
        floor_datum=Datum.SFC,
        ceiling_ft=18000.0,
        ceiling_datum=Datum.MSL,
        activation=Activation.ALWAYS,
    )


def test_flags_a_state_inside_the_polygon() -> None:
    """The default state sits inside P-901, so contained is True and penetration
    is a real distance."""
    result = check_containment(make_state(), [make_p901()], load_config())
    assert result.contained is True
    assert "P-901" in result.zone_ids
    assert result.penetration_nm is not None
    # Nearest edge is 0.025 degrees of latitude away, about 1.5 nm.
    assert result.penetration_nm == pytest.approx(1.5, abs=0.05)
    assert result.reason is None


def test_reports_outside_polygon_when_clear() -> None:
    """A state east of KLYH hits nothing, and the result carries a reason rather
    than returning None."""
    result = check_containment(
        make_state(lat=37.10, lon=-78.80), [make_p901()], load_config()
    )
    assert result.contained is False
    assert result.buffered_contained is False
    assert result.penetration_nm is None
    assert result.reason is ExitReason.OUTSIDE_POLYGON


def test_just_outside_with_poor_accuracy_is_buffered_only() -> None:
    """About 55 m south of the fence with NIC 6 (radius ~1.1 km): not strictly
    inside, but within the position uncertainty, so buffered_contained is True."""
    result = check_containment(
        make_state(lat=37.3995, lon=-79.215, nic=6), [make_p901()], load_config()
    )
    assert result.contained is False
    assert result.buffered_contained is True
    assert result.zone_ids == ("P-901",)
    assert result.penetration_nm is None


def test_empty_zone_list_reports_no_candidate() -> None:
    """Nothing to test is a normal answer, with a reason, never None."""
    result = check_containment(make_state(), [], load_config())
    assert result.contained is False
    assert result.zone_ids == ()
    assert result.reason is ExitReason.NO_CANDIDATE