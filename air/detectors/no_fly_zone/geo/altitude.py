"""Stream D - vertical containment.

A zone is a volume, not a footprint. An aircraft inside the polygon at FL350
over a surface-to-3000 ft restricted area has violated nothing. This stage
compares the aircraft's altitude to one zone's floor/ceiling band after putting
both on a common reference.

Inputs
------
state:
    Supplies ``alt_geom_ft`` and ``alt_baro_ft``. Geometric altitude is preferred
    for MSL / SFC limits because MSL floors and ceilings are true heights above
    sea level. Barometric (pressure) altitude is preferred for FL (Flight Level)
    limits because Flight Levels are standard pressure altitudes (referenced to
    1013.25 hPa / 29.92 inHg). Each falls back to the other when unavailable.
zone:
    Supplies ``floor_ft``/``floor_datum`` and ``ceiling_ft``/``ceiling_datum``.

Outputs
-------
A :class:`VerticalResult` carrying the value actually compared, which
:class:`AltitudeSource` it came from, and whether it fell inside the band.

Failure causes
--------------
Both altitude fields ``None``
    Returns ``within=False``, ``altitude_source=NONE``,
    ``reason=ExitReason.BAD_INPUT``. Abstain; never guess an altitude.
:attr:`Datum.AGL`
    Needs a terrain model this detector does not have. Abstain with
    ``BAD_INPUT`` rather than silently comparing an AGL floor to an MSL
    altitude, which would be wrong by the terrain elevation.

Notes
-----
:attr:`Datum.FL` values are stored in feet (FL180 -> 18000) and represent
pressure altitude, so they are compared against ``state.alt_baro_ft`` (falling
back to ``state.alt_geom_ft``). :attr:`Datum.SFC` is stored as 0.
"""
from __future__ import annotations

from ..types import (
    AircraftState,
    AirspaceZone,
    AltitudeSource,
    Datum,
    ExitReason,
    VerticalResult,
)


def _resolve_altitude(
    state: AircraftState, datum: Datum
) -> tuple[float, AltitudeSource]:
    """Resolve the aircraft altitude and source appropriate for ``datum``.

    FL limits are standard pressure altitudes, so barometric altitude is preferred.
    MSL and SFC limits are geometric heights, so geometric altitude is preferred.
    Each falls back to the other available altitude if the preferred one is None.
    """
    
    if datum == Datum.FL:
        if state.alt_baro_ft is not None:
            return state.alt_baro_ft, AltitudeSource.BAROMETRIC
        assert state.alt_geom_ft is not None
        return state.alt_geom_ft, AltitudeSource.GEOMETRIC
    else:
        if state.alt_geom_ft is not None:
            return state.alt_geom_ft, AltitudeSource.GEOMETRIC
        assert state.alt_baro_ft is not None
        return state.alt_baro_ft, AltitudeSource.BAROMETRIC


def vertical_check(state: AircraftState, zone: AirspaceZone) -> VerticalResult:
    """Compare ``state``'s altitude to ``zone``'s floor/ceiling band."""
    # -------------------------------------------------------------------------
    # 1. Validate available altitudes
    # If neither altitude is available, abstain with BAD_INPUT (never guess).
    # -------------------------------------------------------------------------
    if state.alt_geom_ft is None and state.alt_baro_ft is None:
        return VerticalResult(
            within=False,
            altitude_ft=None,
            altitude_source=AltitudeSource.NONE,
            reason=ExitReason.BAD_INPUT,
        )

    # -------------------------------------------------------------------------
    # 2. Validate zone datums
    # AGL (Above Ground Level) requires a terrain elevation model that this
    # detector lacks. Comparing AGL directly against MSL/FL would produce
    # significant errors, so abstain with BAD_INPUT when AGL is encountered.
    # -------------------------------------------------------------------------
    if zone.floor_datum == Datum.AGL or zone.ceiling_datum == Datum.AGL:
        default_alt = (
            state.alt_geom_ft
            if state.alt_geom_ft is not None
            else state.alt_baro_ft
        )
        default_source = (
            AltitudeSource.GEOMETRIC
            if state.alt_geom_ft is not None
            else AltitudeSource.BAROMETRIC
        )
        return VerticalResult(
            within=False,
            altitude_ft=default_alt,
            altitude_source=default_source,
            reason=ExitReason.BAD_INPUT,
        )

    # -------------------------------------------------------------------------
    # 3. Resolve altitude values for each boundary datum
    # MSL/SFC boundaries are geometric heights above sea level, so geometric
    # altitude is preferred, falling back to barometric.
    # FL (Flight Level) boundaries are pressure altitudes, so barometric
    # altitude is preferred, falling back to geometric.
    # -------------------------------------------------------------------------
    floor_alt, floor_source = _resolve_altitude(state, zone.floor_datum)
    ceiling_alt, ceiling_source = _resolve_altitude(state, zone.ceiling_datum)

    # -------------------------------------------------------------------------
    # 4. Check vertical containment within the [floor_ft, ceiling_ft] band
    # If the aircraft is cleanly above or below the band, report VERTICAL_CLEAR
    # with the altitude value that was compared against that boundary.
    # -------------------------------------------------------------------------
    if floor_alt < zone.floor_ft:
        return VerticalResult(
            within=False,
            altitude_ft=floor_alt,
            altitude_source=floor_source,
            reason=ExitReason.VERTICAL_CLEAR,
        )

    if ceiling_alt > zone.ceiling_ft:
        return VerticalResult(
            within=False,
            altitude_ft=ceiling_alt,
            altitude_source=ceiling_source,
            reason=ExitReason.VERTICAL_CLEAR,
        )

    # -------------------------------------------------------------------------
    # 5. Aircraft is within the band
    # If both datums are FL, record barometric altitude. Otherwise, record
    # geometric altitude (if available) as the primary physical position.
    # -------------------------------------------------------------------------
    if zone.floor_datum == Datum.FL and zone.ceiling_datum == Datum.FL:
        within_alt, within_source = ceiling_alt, ceiling_source
    elif state.alt_geom_ft is not None:
        within_alt, within_source = state.alt_geom_ft, AltitudeSource.GEOMETRIC
    else:
        assert state.alt_baro_ft is not None
        within_alt, within_source = state.alt_baro_ft, AltitudeSource.BAROMETRIC

    return VerticalResult(
        within=True,
        altitude_ft=within_alt,
        altitude_source=within_source,
        reason=None,
    )

