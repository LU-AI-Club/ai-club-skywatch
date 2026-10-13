"""LEAD-OWNED - wires the stages together. No detection logic lives here.

The pipeline, in order, with the :class:`ExitReason` recorded when a state
leaves without a detection:

    H3 coarse filter      -> NO_CANDIDATE
    exact containment     -> OUTSIDE_POLYGON
    vertical check        -> VERTICAL_CLEAR
    activation            -> ZONE_INACTIVE
    context signals       -> (never exits; only lowers the score)
    score / emit          -> a Detection

``filters.drop_on_ground`` short-circuits to :attr:`ExitReason.ON_GROUND`
before any geometry runs, because a taxiing aircraft inside an airport-adjacent
zone is not an incursion.

Inputs
------
states:
    The stream A iterator.
zones:
    The stream B list.
cfg:
    The loaded config, passed down to every stage.

Outputs
-------
An iterator of :class:`Detection`. Exit reasons are counted, not returned, so
the CLI can report why states dropped out - a detector that emits nothing and
cannot say why is untestable.

Failure causes
--------------
Whatever the stages raise. This module adds no failure modes of its own; if it
grows a branch that decides something, that branch belongs in a stage module.

Notes
-----
This module may import from every stage. The stages may not import each other
- that one-way rule is what lets each stream be owned and tested alone.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator

from ..config import Config
from ..types import AircraftState, AirspaceZone, Detection


def run(
    states: Iterable[AircraftState], zones: list[AirspaceZone], cfg: Config
) -> Iterator[Detection]:
    """Run the full pipeline over ``states``, yielding detections."""
    raise NotImplementedError("lead: detector wiring")
