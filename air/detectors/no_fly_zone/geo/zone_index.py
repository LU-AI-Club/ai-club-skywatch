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

import functools
import weakref
from collections.abc import Sequence

import h3
import shapely

from ..config import Config
from ..types import AircraftState, AirspaceZone

_BUFFER_RINGS = 1  # structural, not tunable: the docstring's one-ring recall guarantee


def _resolution(cfg: Config) -> int:
    res = cfg.raw.get("geometry", {}).get("h3_resolution")
    # bool first: True is an int in Python and would quietly mean resolution 1.
    if isinstance(res, bool) or not isinstance(res, int) or not 0 <= res <= 15:
        raise ValueError(f"geometry.h3_resolution must be an int 0-15, got {res!r}")
    return res


# Per geometry object: (id(geometry), res) -> cells. Looking the cells up by
# WKB meant serializing every zone's full outline on every position report just
# to build the cache key - 85% of NFZ's run time with the real FAA zones (some
# have 6-8k vertices). Each entry is dropped when its geometry is freed, so a
# reused id can never be served another zone's cells.
_CELLS_BY_GEOMETRY: dict[tuple[int, int], frozenset[str]] = {}


def _zone_cells(zone: AirspaceZone, res: int) -> frozenset[str]:
    geometry = zone.geometry
    key = (id(geometry), res)
    cells = _CELLS_BY_GEOMETRY.get(key)
    if cells is None:
        cells = _cells_for_geometry(geometry.wkb, res)
        _CELLS_BY_GEOMETRY[key] = cells
        weakref.finalize(geometry, _CELLS_BY_GEOMETRY.pop, key, None)
    return cells


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


# Inverted index: H3 cell -> positions (in ``zones``) of the zones covering it.
# Built once per zone list and resolution, so a report costs seven dict lookups
# however many zones there are, instead of one set intersection per zone.
#
# Keyed on the identity of the ``zones`` sequence: every caller passes the same
# list for a whole run (the adapter's ``self.zones``, the CLI's loaded list), and
# hashing every zone on every report to build a content key would bring back the
# per-zone cost this index removes. Each entry holds a reference to its list, so
# an id cannot be reused while the entry exists, and records the list's length
# as a cheap guard against in-place edits. Treat ``zones`` as read-only for the
# life of a run; pass a new list to change the zones. A few entries are kept
# (tests build many lists), oldest dropped first.
_INDEX_CACHE_SIZE = 8  # structural, not tunable: bounds memory held by stale lists
_ZoneIndex = dict[str, tuple[int, ...]]
_INDEXES: dict[tuple[int, int], tuple[Sequence[AirspaceZone], int, _ZoneIndex]] = {}


def _build_index(zones: Sequence[AirspaceZone], res: int) -> _ZoneIndex:
    positions_by_cell: dict[str, list[int]] = {}
    for position, zone in enumerate(zones):
        for cell in _zone_cells(zone, res):
            positions_by_cell.setdefault(cell, []).append(position)
    return {cell: tuple(positions) for cell, positions in positions_by_cell.items()}


def _index_for(zones: Sequence[AirspaceZone], res: int) -> _ZoneIndex:
    key = (id(zones), res)
    entry = _INDEXES.get(key)
    if entry is not None and entry[0] is zones and entry[1] == len(zones):
        return entry[2]
    index = _build_index(zones, res)
    _INDEXES.pop(key, None)
    while len(_INDEXES) >= _INDEX_CACHE_SIZE:
        del _INDEXES[next(iter(_INDEXES))]
    _INDEXES[key] = (zones, len(zones), index)
    return index


def candidate_zone_ids(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> tuple[str, ...]:
    """Return ids of zones close enough to deserve an exact test.

    Same result, in the same order (the order of ``zones``), as testing every
    zone's cells against the aircraft's buffered cell; see the index notes above.
    """
    res = _resolution(cfg)
    index = _index_for(zones, res)
    plane_cell = h3.latlng_to_cell(state.lat, state.lon, res)
    # Buffering the plane's cell is equivalent to buffering every zone cell,
    # and costs one disk instead of one per zone cell.
    positions: set[int] = set()
    for cell in h3.grid_disk(plane_cell, _BUFFER_RINGS):
        positions.update(index.get(cell, ()))
    return tuple(zones[position].zone_id for position in sorted(positions))
