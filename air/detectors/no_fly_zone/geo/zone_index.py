"""Stream C (part 1) - H3 coarse filter.

Running point-in-polygon against every zone within 150 nm is wasteful: almost
every observation is nowhere near a restricted volume. This narrows the field
to the few zones sharing the aircraft's H3 cell, so the exact test in
``containment.py`` runs on a short list.

Inputs
------
state:
    The observation to place.
zones:
    Every candidate zone, typically the full output of stream B.
cfg:
    Supplies ``geometry.h3_resolution`` (res 7, ~5 km cells, matches SENTINEL)
    and ``geometry.default_uncertainty_m``, used when NIC is absent or 0.

Outputs
-------
A tuple of ``zone_id`` values worth testing exactly. Empty is a normal result
and the caller records :attr:`ExitReason.NO_CANDIDATE`.

Failure causes
--------------
ValueError
    ``geometry.h3_resolution`` is missing or outside the valid H3 range 0-15.

Notes
-----
This is a *recall* filter: it must never drop a zone the exact test would have
hit. Buffer each zone's cell set by one ring so an aircraft just outside a
boundary still surfaces for the buffered-containment check.

That one ring spans only about one cell edge (~1.3 km at res 7). The buffered
check in ``containment.py`` reaches out to the position-uncertainty radius,
which is 3.7 km at NIC 4 and 14.8 km at NIC 2, so one ring alone would drop
those zones before the exact test ever saw them. The ring count therefore
grows with the radius: one base ring, plus enough rings to span the radius at
the shortest edge of the aircraft's own cell.
"""
from __future__ import annotations

import functools
import math
from collections.abc import Sequence

import h3
import shapely

from ..config import Config
from ..types import AircraftState, AirspaceZone

_BASE_RINGS = 1  # structural, not tunable: the docstring's one-ring recall guarantee

# ADS-B NIC -> horizontal containment radius in metres (DO-260B Rc values).
# Duplicated from geo/containment.py on purpose (modules never cross-import);
# keep the two tables identical or this filter drops zones that check buffers.
_NIC_RADIUS_M: dict[int, float] = {
    11: 7.5, 10: 25.0, 9: 75.0, 8: 185.2, 7: 370.4, 6: 1111.2,
    5: 1852.0, 4: 3704.0, 3: 7408.0, 2: 14816.0, 1: 37040.0,
}


def _resolution(cfg: Config) -> int:
    res = cfg.raw.get("geometry", {}).get("h3_resolution")
    # bool first: True is an int in Python and would quietly mean resolution 1.
    if isinstance(res, bool) or not isinstance(res, int) or not 0 <= res <= 15:
        raise ValueError(f"geometry.h3_resolution must be an int 0-15, got {res!r}")
    return res


def _uncertainty_m(state: AircraftState, cfg: Config) -> float:
    """Position uncertainty radius in metres, matching containment.py."""
    if state.nic is not None and state.nic in _NIC_RADIUS_M:
        return _NIC_RADIUS_M[state.nic]
    return float(cfg["geometry"]["default_uncertainty_m"])


def _ring_count(cell: str, radius_m: float) -> int:
    """Rings around ``cell`` that cover every point within ``radius_m`` of it.

    Each ring pushes the disk's edge out by at least one cell edge, so the
    shortest edge of the aircraft's cell is the conservative step.
    """
    min_edge_m = min(
        float(h3.edge_length(e, "m")) for e in h3.origin_to_directed_edges(cell)
    )
    return _BASE_RINGS + math.ceil(radius_m / min_edge_m)


def _zone_cells(zone: AirspaceZone, res: int) -> frozenset[str]:
    return _cells_for_geometry(zone.geometry.wkb, res)


# Covering a zone with cells is the expensive step (milliseconds for a large
# MOA) and its answer never changes for the same geometry and resolution, yet
# it is asked once per zone for every position report. Memoizing it keeps the
# function pure - same input, same output, no I/O - and cuts a call over ~20
# zones from ~5 ms to ~0.1 ms. Keyed on the geometry's bytes, not the zone id,
# so a redrawn zone can never be served stale cells.
@functools.lru_cache(maxsize=1024)
def _cells_for_geometry(wkb: bytes, res: int) -> frozenset[str]:
    geometry = shapely.from_wkb(wkb)
    # geo_to_h3shape reads GeoJSON lon/lat order, so no manual swap is needed.
    shape = h3.geo_to_h3shape(geometry.__geo_interface__)
    # "overlap", not the default "center": a zone smaller than one cell can
    # contain no cell centers and would otherwise get no cells at all.
    return frozenset(h3.h3shape_to_cells_experimental(shape, res, contain="overlap"))


def candidate_zone_ids(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> tuple[str, ...]:
    """Return ids of zones close enough to deserve an exact test."""
    res = _resolution(cfg)
    plane_cell = h3.latlng_to_cell(state.lat, state.lon, res)
    # Buffering the plane's cell is equivalent to buffering every zone cell,
    # and costs one disk instead of one per zone cell.
    rings = _ring_count(plane_cell, _uncertainty_m(state, cfg))
    nearby = set(h3.grid_disk(plane_cell, rings))
    return tuple(zone.zone_id for zone in zones if nearby & _zone_cells(zone, res))
