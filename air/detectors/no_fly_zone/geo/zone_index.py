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

from ..config import Config
from ..types import AircraftState, AirspaceZone


def candidate_zone_ids(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> tuple[str, ...]:
    """Return ids of zones close enough to deserve an exact test."""
    raise NotImplementedError("stream C: zone_index")
