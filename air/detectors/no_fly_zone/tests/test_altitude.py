"""Stream D tests - geo/altitude.py."""
from __future__ import annotations

from ..geo.altitude import vertical_check
from ..ingest.airspace_loader import load_zones
from ..types import AltitudeSource, ExitReason
from .conftest import AIRSPACE_FILE, make_state


def _zone(zone_id: str):  # type: ignore[no-untyped-def]
    return next(z for z in load_zones(AIRSPACE_FILE) if z.zone_id == zone_id)


def test_altitude_inside_the_band_is_within() -> None:
    """5200 ft geometric against P-901's SFC-18000 band is inside, and the result
    records that geometric altitude was the value compared."""
    result = vertical_check(make_state(), _zone("P-901"))
    assert result.within is True
    assert result.altitude_source is AltitudeSource.GEOMETRIC
    assert result.altitude_ft == 5200.0


def test_abstains_when_both_altitudes_are_missing() -> None:
    """No altitude means abstain with BAD_INPUT. Never guess an altitude."""
    result = vertical_check(make_state(alt_baro_ft=None, alt_geom_ft=None), _zone("P-901"))
    assert result.within is False
    assert result.reason is ExitReason.BAD_INPUT


def test_above_the_ceiling_is_vertical_clear() -> None:
    result = vertical_check(make_state(alt_geom_ft=35000.0), _zone("P-901"))
    assert result.reason is ExitReason.VERTICAL_CLEAR


def test_barometric_fallback_is_recorded() -> None:
    result = vertical_check(make_state(alt_geom_ft=None), _zone("P-901"))
    assert result.within is True
    assert result.altitude_source is AltitudeSource.BAROMETRIC
