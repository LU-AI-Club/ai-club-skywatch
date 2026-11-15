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
    An AGL limit is a height above the ground, and the detector has no terrain
    model. It has, at best, the lowest and highest ground elevation under the
    zone (``zone.terrain_min_ft`` / ``zone.terrain_max_ft``), so the limit is
    somewhere in ``[limit + terrain_min, limit + terrain_max]`` ft MSL. An
    aircraft clear of that whole range is decided either way; an aircraft
    inside it abstains with ``BAD_INPUT``, as does any AGL limit on a zone with
    no terrain bound. Never compares an AGL limit to an MSL altitude directly,
    which would be wrong by the terrain elevation.

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
    MSL, SFC and AGL limits are geometric heights, so geometric altitude is preferred.
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


def _limit_range_ft(
    value_ft: float, datum: Datum, zone: AirspaceZone
) -> tuple[float, float] | None:
    """The lowest and highest ft MSL a floor or ceiling can be.

    One value for MSL/SFC/FL limits. An AGL limit sits on the ground, so it
    spans the zone's terrain bound; ``None`` when the zone has none.
    """
    if datum is not Datum.AGL:
        return value_ft, value_ft
    if zone.terrain_min_ft is None or zone.terrain_max_ft is None:
        return None
    return value_ft + zone.terrain_min_ft, value_ft + zone.terrain_max_ft


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
    # 2. Resolve the altitude to compare against each limit
    # MSL/SFC/AGL limits are heights, so geometric altitude is preferred,
    # falling back to barometric. FL limits are pressure altitudes, so
    # barometric is preferred, falling back to geometric.
    # -------------------------------------------------------------------------
    floor_alt, floor_source = _resolve_altitude(state, zone.floor_datum)
    ceiling_alt, ceiling_source = _resolve_altitude(state, zone.ceiling_datum)

    # -------------------------------------------------------------------------
    # 3. Put each limit in ft MSL as a (lowest, highest) range
    # Equal for MSL/SFC/FL. For AGL the range is as wide as the terrain under
    # the zone, and None when the zone carries no terrain bound.
    # -------------------------------------------------------------------------
    floor_range = _limit_range_ft(zone.floor_ft, zone.floor_datum, zone)
    ceiling_range = _limit_range_ft(zone.ceiling_ft, zone.ceiling_datum, zone)

    # -------------------------------------------------------------------------
    # 4. Cleanly below the floor or above the ceiling: VERTICAL_CLEAR
    # Decided first, so an aircraft above an MSL ceiling is clear even when the
    # zone's AGL floor cannot be placed.
    # -------------------------------------------------------------------------
    if floor_range is not None and floor_alt < floor_range[0]:
        return VerticalResult(
            within=False,
            altitude_ft=floor_alt,
            altitude_source=floor_source,
            reason=ExitReason.VERTICAL_CLEAR,
        )

    if ceiling_range is not None and ceiling_alt > ceiling_range[1]:
        return VerticalResult(
            within=False,
            altitude_ft=ceiling_alt,
            altitude_source=ceiling_source,
            reason=ExitReason.VERTICAL_CLEAR,
        )

    # -------------------------------------------------------------------------
    # 4b. An AGL limit that cannot be placed, or an aircraft inside the range
    # an AGL limit could be anywhere in: abstain with BAD_INPUT, never guess.
    # -------------------------------------------------------------------------
    if (
        floor_range is None
        or ceiling_range is None
        or floor_alt < floor_range[1]
        or ceiling_alt > ceiling_range[0]
    ):
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

