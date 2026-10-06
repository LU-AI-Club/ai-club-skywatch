"""Stream D tests - geo/altitude.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import Polygon

from ..geo.altitude import vertical_check
from ..types import (
    Activation,
    AirspaceZone,
    AltitudeSource,
    Datum,
    ExitReason,
    ZoneType,
)
from .conftest import make_state


def make_zone(**overrides: Any) -> AirspaceZone:
    """Build a minimal AirspaceZone for testing."""
    base: dict[str, Any] = {
        "zone_id": "P-901",
        "name": "P-901 Prohibited Area",
        "zone_type": ZoneType.PROHIBITED,
        "geometry": Polygon(),
        "floor_ft": 0.0,
        "floor_datum": Datum.SFC,
        "ceiling_ft": 18000.0,
        "ceiling_datum": Datum.MSL,
        "activation": Activation.ALWAYS,
    }
    base.update(overrides)
    return AirspaceZone(**base)


def test_altitude_inside_the_band_is_within() -> None:
    """5200 ft geometric against P-901's SFC-18000 band is inside, and the result
    records that geometric altitude was the value compared."""
    state = make_state(alt_geom_ft=5200.0)
    zone = make_zone()
    res = vertical_check(state, zone)
    assert res.within is True
    assert res.altitude_source is AltitudeSource.GEOMETRIC
    assert res.altitude_ft == 5200.0
    assert res.reason is None


def test_abstains_when_both_altitudes_are_missing() -> None:
    """No altitude means abstain with BAD_INPUT. Never guess an altitude."""
    state = make_state(alt_baro_ft=None, alt_geom_ft=None)
    zone = make_zone()
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.NONE
    assert res.reason is ExitReason.BAD_INPUT


def test_falls_back_to_barometric_when_geometric_is_none() -> None:
    """Barometric is used if geometric is None."""
    state = make_state(alt_geom_ft=None, alt_baro_ft=4850.0)
    zone = make_zone()
    res = vertical_check(state, zone)
    assert res.within is True
    assert res.altitude_source is AltitudeSource.BAROMETRIC
    assert res.altitude_ft == 4850.0
    assert res.reason is None


def test_reports_vertical_clear_when_above_ceiling() -> None:
    """Aircraft above zone ceiling exits with VERTICAL_CLEAR."""
    state = make_state(alt_geom_ft=35000.0)
    zone = make_zone(ceiling_ft=18000.0)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_reports_vertical_clear_when_below_floor() -> None:
    """Aircraft below zone floor exits with VERTICAL_CLEAR."""
    state = make_state(alt_geom_ft=1000.0)
    zone = make_zone(floor_ft=3000.0, floor_datum=Datum.MSL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_abstains_when_datum_is_agl() -> None:
    """AGL datum cannot be compared without a terrain model; abstains with BAD_INPUT."""
    state = make_state(alt_geom_ft=5200.0)
    zone = make_zone(floor_datum=Datum.AGL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.GEOMETRIC
    assert res.reason is ExitReason.BAD_INPUT

