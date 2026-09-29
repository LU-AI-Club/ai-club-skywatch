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
from functools import lru_cache

import h3
from shapely import wkb
from shapely.geometry import mapping

from ..config import Config
from ..types import AircraftState, AirspaceZone

_H3_MIN_RES = 0
_H3_MAX_RES = 15


def candidate_zone_ids(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> tuple[str, ...]:
    """Return ids of zones close enough to deserve an exact test.

    Raises:
        ValueError: ``geometry.h3_resolution`` is missing or outside 0-15.
    """
    try:
        resolution = int(cfg["geometry"]["h3_resolution"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("geometry.h3_resolution is missing or not an integer") from exc
    if not _H3_MIN_RES <= resolution <= _H3_MAX_RES:
        raise ValueError(f"geometry.h3_resolution {resolution} is outside 0-15")

    cell = h3.latlng_to_cell(state.lat, state.lon, resolution)
    return tuple(
        zone.zone_id for zone in zones if cell in _zone_cells(zone.geometry.wkb, resolution)
    )


@lru_cache(maxsize=256)
def _zone_cells(geometry_wkb: bytes, resolution: int) -> frozenset[str]:
    """Cells overlapping the zone, grown by one ring.

    Memoized on the geometry bytes, so it is a pure function of its inputs: a
    live run re-tests the same few zones for every aircraft every cycle, and
    re-filling each polygon per aircraft was the slow part. ``overlap`` keeps
    cells the boundary merely clips (a small prohibited area can be narrower
    than one cell), and the extra ring lets a state just outside the fence
    reach the buffered test.
    """
    geometry = wkb.loads(geometry_wkb)
    polygons = list(getattr(geometry, "geoms", [geometry]))
    cells: set[str] = set()
    for polygon in polygons:
        shape = h3.geo_to_h3shape(mapping(polygon))
        cells.update(h3.h3shape_to_cells_experimental(shape, resolution, contain="overlap"))
        for lon, lat in polygon.exterior.coords:
            cells.add(h3.latlng_to_cell(lat, lon, resolution))
    grown: set[str] = set()
    for cell in cells:
        grown.update(h3.grid_disk(cell, 1))
    return frozenset(grown)
