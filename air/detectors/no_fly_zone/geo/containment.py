"""Stream C (part 2) - exact horizontal containment.

Decides whether the aircraft is inside a zone's polygon and how far inside.
Runs the strict point-in-polygon test *and* a buffered test that grows the
point by its position uncertainty: an aircraft reporting a poor NIC while
sitting 50 m outside the fence is not a confident clear.

Inputs
------
state:
    The observation to test.
zones:
    The short list from :func:`zone_index.candidate_zone_ids`. Passing the full
    set works but is slow.
cfg:
    Supplies ``geometry.default_uncertainty_m``, used when NIC/NACp are absent.

Outputs
-------
A :class:`ContainmentResult`. ``contained`` is the strict test,
``buffered_contained`` the uncertainty-aware one, ``penetration_nm`` the
distance inside the boundary (``None`` when outside), and ``zone_ids`` every
zone hit by either test.

Failure causes
--------------
ValueError
    A zone geometry is not a valid polygon.

Nothing hit is not an exception: the result carries
:attr:`ExitReason.OUTSIDE_POLYGON`, or :attr:`ExitReason.NO_CANDIDATE` when
``zones`` was empty. Never returns ``None``.

Notes
-----
DEVIATION from the CLAUDE.md signature table, which lists
``check_containment(state, zones)``. ``cfg`` is a required third argument
because ``default_uncertainty_m`` has to be passed in, never read inside a
module. Those two hard rules conflict; the lead should settle it.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from ..config import Config
from ..types import AircraftState, AirspaceZone, ContainmentResult, ExitReason

# Unit conversions. These are physical constants, not tunables, but the
# "no constants inline" rule means they are named here instead of buried in
# the maths. ASK THE LEAD whether they belong in config.yaml.
_M_PER_NM = 1852.0
_NM_PER_DEG_LAT = 60.0

# ADS-B NIC -> horizontal containment radius in metres (DO-260B Rc values).
# NIC 0 means "unknown", so it falls back to cfg geometry.default_uncertainty_m.
# ASK THE LEAD to confirm this table and decide whether it moves to config.yaml.
_NIC_RADIUS_M: dict[int, float] = {
    11: 7.5, 10: 25.0, 9: 75.0, 8: 185.2, 7: 370.4, 6: 1111.2,
    5: 1852.0, 4: 3704.0, 3: 7408.0, 2: 14816.0, 1: 37040.0,
}


def _uncertainty_m(state: AircraftState, cfg: Config) -> float:
    """Position uncertainty radius in metres for this observation."""
    if state.nic is not None and state.nic in _NIC_RADIUS_M:
        return _NIC_RADIUS_M[state.nic]
    return float(cfg["geometry"]["default_uncertainty_m"])


def _to_local_nm(geometry: BaseGeometry, lat0: float, lon0: float) -> BaseGeometry:
    """Re-express a lon/lat geometry in nautical miles, with the aircraft at (0, 0).

    Degrees of longitude shrink as you move away from the equator, so the
    east-west axis is scaled by cos(latitude). That is accurate enough over
    the few nautical miles that matter here.
    """
    x_scale = math.cos(math.radians(lat0)) * _NM_PER_DEG_LAT

    def _project(x: float, y: float, z: float | None = None) -> tuple[float, float]:
        return ((x - lon0) * x_scale, (y - lat0) * _NM_PER_DEG_LAT)

    return transform(_project, geometry)


def check_containment(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> ContainmentResult:
    """Test ``state`` against ``zones`` horizontally, strictly and buffered."""
    radius_m = _uncertainty_m(state, cfg)

    # Nothing to test is a normal answer, and it carries a reason.
    if not zones:
        return ContainmentResult(
            contained=False,
            buffered_contained=False,
            zone_ids=(),
            penetration_nm=None,
            uncertainty_radius_m=radius_m,
            reason=ExitReason.NO_CANDIDATE,
        )

    radius_nm = radius_m / _M_PER_NM
    origin = Point(0.0, 0.0)  # the aircraft, in the local frame

    hit_ids: list[str] = []
    contained = False
    buffered_contained = False
    deepest_nm: float | None = None

    for zone in zones:
        geometry = zone.geometry
        if geometry.geom_type not in ("Polygon", "MultiPolygon") or not geometry.is_valid:
            raise ValueError(f"zone {zone.zone_id} does not have a valid polygon geometry")

        local = _to_local_nm(geometry, state.lat, state.lon)

        strictly_inside = bool(local.covers(origin))
        within_uncertainty = strictly_inside or local.distance(origin) <= radius_nm
        if not within_uncertainty:
            continue

        hit_ids.append(zone.zone_id)
        buffered_contained = True
        if strictly_inside:
            contained = True
            depth_nm = float(local.boundary.distance(origin))
            if deepest_nm is None or depth_nm > deepest_nm:
                deepest_nm = depth_nm

    return ContainmentResult(
        contained=contained,
        buffered_contained=buffered_contained,
        zone_ids=tuple(hit_ids),
        penetration_nm=deepest_nm,
        uncertainty_radius_m=radius_m,
        reason=None if hit_ids else ExitReason.OUTSIDE_POLYGON,
    )