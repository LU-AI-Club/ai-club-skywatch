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

from collections.abc import Callable, Sequence
from math import cos, radians

from shapely.geometry import Point
from shapely.ops import transform

from ..config import Config
from ..types import AircraftState, AirspaceZone, ContainmentResult, ExitReason

_M_PER_NM = 1852.0
_M_PER_DEG_LAT = 111_132.954
_M_PER_DEG_LON_EQUATOR = 111_319.49

# DO-260B containment radius (Rc) for each NIC value, in meters. These are the
# definitions of the NIC field, not tunables. NIC 0 means "unknown", which is
# treated as missing so the configured default applies.
_NIC_RADIUS_M = {
    11: 7.5,
    10: 25.0,
    9: 75.0,
    8: 185.2,
    7: 370.4,
    6: 1111.2,
    5: 1852.0,
    4: 3704.0,
    3: 7408.0,
    2: 14816.0,
    1: 37040.0,
}


def check_containment(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> ContainmentResult:
    """Test ``state`` against ``zones`` horizontally, strictly and buffered.

    Raises:
        ValueError: A zone geometry is not a valid polygon.
    """
    radius_m = uncertainty_radius_m(state, cfg)
    if not zones:
        return ContainmentResult(
            contained=False,
            buffered_contained=False,
            zone_ids=(),
            penetration_nm=None,
            uncertainty_radius_m=radius_m,
            reason=ExitReason.NO_CANDIDATE,
        )

    project = _local_projection(state.lat, state.lon)
    here = Point(0.0, 0.0)
    strict: list[tuple[str, float]] = []
    buffered: list[str] = []
    for zone in zones:
        if zone.geometry.geom_type not in ("Polygon", "MultiPolygon") or not zone.geometry.is_valid:
            raise ValueError(f"{zone.zone_id}: geometry is not a valid polygon")
        local = transform(project, zone.geometry)
        if local.contains(here):
            strict.append((zone.zone_id, local.boundary.distance(here) / _M_PER_NM))
        elif local.distance(here) <= radius_m:
            buffered.append(zone.zone_id)

    hit_ids = tuple(zone_id for zone_id, _ in strict) + tuple(buffered)
    return ContainmentResult(
        contained=bool(strict),
        buffered_contained=bool(hit_ids),
        zone_ids=hit_ids,
        penetration_nm=max((depth for _, depth in strict), default=None),
        uncertainty_radius_m=radius_m,
        reason=None if hit_ids else ExitReason.OUTSIDE_POLYGON,
    )


def uncertainty_radius_m(state: AircraftState, cfg: Config) -> float:
    """Horizontal position uncertainty: NIC's radius, else the configured default."""
    if state.nic is not None and state.nic in _NIC_RADIUS_M:
        return _NIC_RADIUS_M[state.nic]
    return float(cfg["geometry"]["default_uncertainty_m"])


def _local_projection(lat0: float, lon0: float) -> Callable[..., tuple[float, float]]:
    """Equirectangular meters around the aircraft. Accurate to well under 1%
    across the few miles that matter for a boundary distance."""
    m_per_deg_lon = _M_PER_DEG_LON_EQUATOR * cos(radians(lat0))

    def project(lon: float, lat: float, z: float | None = None) -> tuple[float, float]:
        return (lon - lon0) * m_per_deg_lon, (lat - lat0) * _M_PER_DEG_LAT

    return project

