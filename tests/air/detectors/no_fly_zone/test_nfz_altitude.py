"""Stream D tests - geo/altitude.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

from typing import Any

from nfz_support import make_state
from shapely.geometry import Polygon

from air.detectors.no_fly_zone.geo.altitude import vertical_check
from air.detectors.no_fly_zone.types import (
    Activation,
    AirspaceZone,
    AltitudeSource,
    Datum,
    ExitReason,
    ZoneType,
)


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


def test_fl_ceiling_uses_barometric_altitude_when_above_ceiling() -> None:
    """FL ceiling is evaluated against barometric pressure altitude.

    An aircraft cruising at FL190 (alt_baro_ft=19000.0) whose geometric altitude
    is lower (17500.0 ft, e.g. on a cold day) is cleanly above the FL180 ceiling.
    """
    state = make_state(alt_baro_ft=19000.0, alt_geom_ft=17500.0)
    zone = make_zone(ceiling_ft=18000.0, ceiling_datum=Datum.FL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.BAROMETRIC
    assert res.altitude_ft == 19000.0
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_fl_ceiling_uses_barometric_altitude_when_inside_band() -> None:
    """FL ceiling uses barometric altitude; plane at FL170 is inside FL180 ceiling

    Even if geometric altitude is 18500.0 ft (e.g. high temperature day), the aircraft
    is maintaining FL170 pressure altitude and is therefore inside the zone.
    """
    state = make_state(alt_baro_ft=17000.0, alt_geom_ft=18500.0)
    zone = make_zone(ceiling_ft=18000.0, ceiling_datum=Datum.FL)
    res = vertical_check(state, zone)
    assert res.within is True
    assert res.reason is None


def test_fl_floor_uses_barometric_altitude() -> None:
    """FL floor is evaluated against barometric altitude.

    An aircraft at FL160 (alt_baro_ft=16000.0) is below an FL180 floor, even if
    its geometric GPS altitude is 18500.0 ft.
    """
    state = make_state(alt_baro_ft=16000.0, alt_geom_ft=18500.0)
    zone = make_zone(
        floor_ft=18000.0,
        floor_datum=Datum.FL,
        ceiling_ft=60000.0,
        ceiling_datum=Datum.FL,
    )
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.BAROMETRIC
    assert res.altitude_ft == 16000.0
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_fl_pure_zone_within_records_barometric_source() -> None:
    """When a zone is defined by FL floor and ceiling, the within result records barometric."""
    state = make_state(alt_baro_ft=35000.0, alt_geom_ft=36200.0)
    zone = make_zone(
        floor_ft=18000.0,
        floor_datum=Datum.FL,
        ceiling_ft=60000.0,
        ceiling_datum=Datum.FL,
    )
    res = vertical_check(state, zone)
    assert res.within is True
    assert res.altitude_source is AltitudeSource.BAROMETRIC
    assert res.altitude_ft == 35000.0
    assert res.reason is None


def test_fl_limit_falls_back_to_geometric_when_barometric_is_missing() -> None:
    """When alt_baro_ft is None, FL limits fall back to geometric altitude."""
    state = make_state(alt_baro_ft=None, alt_geom_ft=35000.0)
    zone = make_zone(ceiling_ft=18000.0, ceiling_datum=Datum.FL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.GEOMETRIC
    assert res.altitude_ft == 35000.0
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_mixed_datums_msl_floor_and_fl_ceiling() -> None:
    """Mixed datums (e.g. MOA with MSL floor and FL ceiling) test each boundary with its datum."""
    # Below MSL floor: geom is 7500 ft (< 8000 MSL), even though baro is 8200 ft
    state_below = make_state(alt_geom_ft=7500.0, alt_baro_ft=8200.0)
    zone = make_zone(
        floor_ft=8000.0,
        floor_datum=Datum.MSL,
        ceiling_ft=18000.0,
        ceiling_datum=Datum.FL,
    )
    res_below = vertical_check(state_below, zone)
    assert res_below.within is False
    assert res_below.altitude_source is AltitudeSource.GEOMETRIC
    assert res_below.altitude_ft == 7500.0
    assert res_below.reason is ExitReason.VERTICAL_CLEAR

    # Above FL ceiling: baro is 19000 ft (> FL180), even though geom is 17500 ft
    state_above = make_state(alt_geom_ft=17500.0, alt_baro_ft=19000.0)
    res_above = vertical_check(state_above, zone)
    assert res_above.within is False
    assert res_above.altitude_source is AltitudeSource.BAROMETRIC
    assert res_above.altitude_ft == 19000.0
    assert res_above.reason is ExitReason.VERTICAL_CLEAR


# --- Error and Edge Case Tests -----------------------------------------------


def test_abstains_when_ceiling_datum_is_agl() -> None:
    """AGL datum on ceiling cannot be evaluated without terrain data; returns BAD_INPUT."""
    state = make_state(alt_geom_ft=5200.0)
    zone = make_zone(ceiling_datum=Datum.AGL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.GEOMETRIC
    assert res.reason is ExitReason.BAD_INPUT


def test_abstains_when_both_datums_are_agl() -> None:
    """Both floor and ceiling as AGL returns BAD_INPUT."""
    state = make_state(alt_geom_ft=2500.0)
    zone = make_zone(floor_datum=Datum.AGL, ceiling_datum=Datum.AGL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.reason is ExitReason.BAD_INPUT


def test_agl_datum_with_barometric_only_records_barometric_source() -> None:
    """When only barometric altitude is available and datum is AGL, source is BAROMETRIC."""
    state = make_state(alt_geom_ft=None, alt_baro_ft=3000.0)
    zone = make_zone(floor_datum=Datum.AGL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.BAROMETRIC
    assert res.altitude_ft == 3000.0
    assert res.reason is ExitReason.BAD_INPUT


def test_both_altitudes_missing_with_agl_datum_abstains_with_none_source() -> None:
    """When both altitudes are None, BAD_INPUT is returned with AltitudeSource.NONE even if AGL."""
    state = make_state(alt_geom_ft=None, alt_baro_ft=None)
    zone = make_zone(floor_datum=Datum.AGL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.altitude_source is AltitudeSource.NONE
    assert res.reason is ExitReason.BAD_INPUT


def test_negative_altitude_below_surface_reports_vertical_clear() -> None:
    """Negative barometric/geometric altitude below a surface floor (0 ft) is VERTICAL_CLEAR."""
    state = make_state(alt_geom_ft=-150.0, alt_baro_ft=-200.0)
    zone = make_zone(floor_ft=0.0, floor_datum=Datum.SFC)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.reason is ExitReason.VERTICAL_CLEAR
    assert res.altitude_ft == -150.0


def test_exact_boundary_edges_inclusive() -> None:
    """Aircraft exactly at floor or ceiling boundary is contained (inclusive comparison)."""
    zone = make_zone(
        floor_ft=1000.0,
        floor_datum=Datum.MSL,
        ceiling_ft=10000.0,
        ceiling_datum=Datum.MSL,
    )

    # Exactly at floor
    res_floor = vertical_check(make_state(alt_geom_ft=1000.0), zone)
    assert res_floor.within is True
    assert res_floor.reason is None

    # Exactly at ceiling
    res_ceil = vertical_check(make_state(alt_geom_ft=10000.0), zone)
    assert res_ceil.within is True
    assert res_ceil.reason is None

    # Fractional distance below floor
    res_below = vertical_check(make_state(alt_geom_ft=999.9), zone)
    assert res_below.within is False
    assert res_below.reason is ExitReason.VERTICAL_CLEAR

    # Fractional distance above ceiling
    res_above = vertical_check(make_state(alt_geom_ft=10000.1), zone)
    assert res_above.within is False
    assert res_above.reason is ExitReason.VERTICAL_CLEAR


def test_inverted_altitude_band_reports_vertical_clear() -> None:
    """Malformed zone where floor > ceiling can never contain an aircraft."""
    zone = make_zone(
        floor_ft=25000.0,
        floor_datum=Datum.MSL,
        ceiling_ft=15000.0,
        ceiling_datum=Datum.MSL,
    )
    state = make_state(alt_geom_ft=20000.0)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_extreme_stratospheric_altitude_reports_vertical_clear() -> None:
    """Extreme altitude (e.g. 100,000+ ft) exits cleanly without numeric issues."""
    state = make_state(alt_geom_ft=120000.0, alt_baro_ft=115000.0)
    zone = make_zone(ceiling_ft=60000.0, ceiling_datum=Datum.MSL)
    res = vertical_check(state, zone)
    assert res.within is False
    assert res.reason is ExitReason.VERTICAL_CLEAR
    assert res.altitude_ft == 120000.0


def test_pin_pressure_vs_geometric_discrepancy() -> None:
    """Pin the discrepancy between geometric altitude and Flight Level (pressure altitude).

    In non-standard atmospheric conditions (e.g. extreme low pressure / cold weather),
    geometric altitude can deviate from pressure altitude by 1,000+ ft.

    This test pins the exact contrast:
    - Against an FL180 ceiling (standard pressure), an aircraft at FL190 (alt_baro=19000 ft)
      is VERTICAL_CLEAR even though its geometric GPS altitude is only 17500 ft.
    - Conversely, against an 18000 MSL ceiling (true geometric height), the same aircraft
      at 17500 ft geometric altitude is within the zone.
    """
    state = make_state(alt_baro_ft=19000.0, alt_geom_ft=17500.0)

    # 1. FL ceiling: must use pressure altitude -> above ceiling, clear
    fl_zone = make_zone(ceiling_ft=18000.0, ceiling_datum=Datum.FL)
    fl_res = vertical_check(state, fl_zone)
    assert fl_res.within is False
    assert fl_res.altitude_source is AltitudeSource.BAROMETRIC
    assert fl_res.altitude_ft == 19000.0
    assert fl_res.reason is ExitReason.VERTICAL_CLEAR

    # 2. MSL ceiling: must use geometric altitude -> below ceiling, within
    msl_zone = make_zone(ceiling_ft=18000.0, ceiling_datum=Datum.MSL)
    msl_res = vertical_check(state, msl_zone)
    assert msl_res.within is True
    assert msl_res.altitude_source is AltitudeSource.GEOMETRIC
    assert msl_res.altitude_ft == 17500.0
    assert msl_res.reason is None



