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

from ..types import AircraftState, AirspaceZone, VerticalResult


def vertical_check(state: AircraftState, zone: AirspaceZone) -> VerticalResult:
    """Compare ``state``'s altitude to ``zone``'s floor/ceiling band."""
    raise NotImplementedError("stream D: altitude")
