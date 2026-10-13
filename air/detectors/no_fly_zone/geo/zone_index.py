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
    Supplies ``geometry.h3_resolution`` (res 7, ~5 km cells, matches SENTINEL).

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
"""
from __future__ import annotations

from collections.abc import Sequence

import h3

from ..config import Config
from ..types import AircraftState, AirspaceZone

_BUFFER_RINGS = 1  # structural, not tunable: the docstring's one-ring recall guarantee


def _resolution(cfg: Config) -> int:
    res = cfg.raw.get("geometry", {}).get("h3_resolution")
    # bool first: True is an int in Python and would quietly mean resolution 1.
    if isinstance(res, bool) or not isinstance(res, int) or not 0 <= res <= 15:
        raise ValueError(f"geometry.h3_resolution must be an int 0-15, got {res!r}")
    return res


def _zone_cells(zone: AirspaceZone, res: int) -> set[str]:
    # geo_to_h3shape reads GeoJSON lon/lat order, so no manual swap is needed.
    shape = h3.geo_to_h3shape(zone.geometry.__geo_interface__)
    # "overlap", not the default "center": a zone smaller than one cell can
    # contain no cell centers and would otherwise get no cells at all.
    return set(h3.h3shape_to_cells_experimental(shape, res, contain="overlap"))


def candidate_zone_ids(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> tuple[str, ...]:
    """Return ids of zones close enough to deserve an exact test."""
    res = _resolution(cfg)
    plane_cell = h3.latlng_to_cell(state.lat, state.lon, res)
    # Buffering the plane's cell is equivalent to buffering every zone cell,
    # and costs one disk instead of one per zone cell.
    nearby = set(h3.grid_disk(plane_cell, _BUFFER_RINGS))
    return tuple(zone.zone_id for zone in zones if nearby & _zone_cells(zone, res))
