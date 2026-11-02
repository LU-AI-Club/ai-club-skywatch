"""Stream D - vertical containment.

A zone is a volume, not a footprint. An aircraft inside the polygon at FL350
over a surface-to-3000 ft restricted area has violated nothing. This stage
compares the aircraft's altitude to one zone's floor/ceiling band after putting
both on a common reference.

Inputs
------
state:
    Supplies ``alt_geom_ft`` and ``alt_baro_ft``. Geometric is preferred when
    present, because MSL floors and ceilings are geometric heights; barometric
    is the fallback and is recorded as such in the result.
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
:attr:`Datum.FL` values are already stored in feet (FL180 -> 18000), so they
need no conversion; :attr:`Datum.SFC` is stored as 0.
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


def vertical_check(state: AircraftState, zone: AirspaceZone) -> VerticalResult:
    """Compare ``state``'s altitude to ``zone``'s floor/ceiling band."""
    # -------------------------------------------------------------------------
    # 1. Resolve altitude source and value
    # Geometric altitude is preferred because MSL floors and ceilings are
    # geometric heights. Barometric altitude is used as a fallback.
    # If neither altitude is available, abstain with BAD_INPUT (never guess).
    # -------------------------------------------------------------------------
    if state.alt_geom_ft is not None:
        alt = state.alt_geom_ft
        source = AltitudeSource.GEOMETRIC
    elif state.alt_baro_ft is not None:
        alt = state.alt_baro_ft
        source = AltitudeSource.BAROMETRIC
    else:
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
    # Note: Datum.FL is pre-stored in feet and Datum.SFC is stored as 0.0.
    # -------------------------------------------------------------------------
    if zone.floor_datum == Datum.AGL or zone.ceiling_datum == Datum.AGL:
        return VerticalResult(
            within=False,
            altitude_ft=alt,
            altitude_source=source,
            reason=ExitReason.BAD_INPUT,
        )

    # -------------------------------------------------------------------------
    # 3. Check vertical containment within the [floor_ft, ceiling_ft] band
    # If the aircraft is within the band, report within=True.
    # Otherwise, it is cleanly above or below the zone, so report VERTICAL_CLEAR.
    # -------------------------------------------------------------------------
    if zone.floor_ft <= alt <= zone.ceiling_ft:
        return VerticalResult(
            within=True,
            altitude_ft=alt,
            altitude_source=source,
            reason=None,
        )

    return VerticalResult(
        within=False,
        altitude_ft=alt,
        altitude_source=source,
        reason=ExitReason.VERTICAL_CLEAR,
    )

