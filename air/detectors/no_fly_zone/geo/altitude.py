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
    """Compare ``state``'s altitude to ``zone``'s floor/ceiling band.

    The band is inclusive at both ends: an aircraft exactly at the ceiling is
    still in the volume. Never raises; abstentions carry ``BAD_INPUT``.
    """
    if state.alt_geom_ft is not None:
        altitude, source = state.alt_geom_ft, AltitudeSource.GEOMETRIC
    elif state.alt_baro_ft is not None:
        altitude, source = state.alt_baro_ft, AltitudeSource.BAROMETRIC
    else:
        return VerticalResult(
            within=False,
            altitude_ft=None,
            altitude_source=AltitudeSource.NONE,
            reason=ExitReason.BAD_INPUT,
        )

    if Datum.AGL in (zone.floor_datum, zone.ceiling_datum):
        # No terrain model: comparing an AGL limit to an MSL altitude would be
        # wrong by the ground elevation, so abstain instead.
        return VerticalResult(
            within=False, altitude_ft=altitude, altitude_source=source, reason=ExitReason.BAD_INPUT
        )

    floor = 0.0 if zone.floor_datum is Datum.SFC else zone.floor_ft
    within = floor <= altitude <= zone.ceiling_ft
    return VerticalResult(
        within=within,
        altitude_ft=altitude,
        altitude_source=source,
        reason=None if within else ExitReason.VERTICAL_CLEAR,
    )
