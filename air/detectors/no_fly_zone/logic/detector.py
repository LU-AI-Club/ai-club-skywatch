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

from collections import Counter
from collections.abc import Iterable, Iterator

from ..config import Config
from ..geo.altitude import vertical_check
from ..geo.containment import check_containment
from ..geo.zone_index import candidate_zone_ids
from ..logic.activation import is_active
from ..logic.context import gather_signals
from ..logic.scoring import build_detection
from ..types import (
    ActivationState,
    AircraftState,
    AirspaceZone,
    Detection,
    ExitReason,
    ZoneType,
)

# How far each exit got, so a state that cleared several zones for different
# reasons is counted once, by the stage it reached last.
_EXIT_ORDER = (
    ExitReason.BAD_INPUT,
    ExitReason.ON_GROUND,
    ExitReason.NO_CANDIDATE,
    ExitReason.OUTSIDE_POLYGON,
    ExitReason.VERTICAL_CLEAR,
    ExitReason.ZONE_INACTIVE,
)


def run(
    states: Iterable[AircraftState],
    zones: list[AirspaceZone],
    cfg: Config,
    exits: Counter[ExitReason] | None = None,
) -> Iterator[Detection]:
    """Run the full pipeline over ``states``, yielding detections.

    ``exits``, when given, is incremented with one :class:`ExitReason` per state
    that produced no detection. Each zone is tested on its own so every
    detection carries that zone's own penetration depth.
    """
    included = {ZoneType(t) for t in cfg["airspace"]["include_types"]}
    usable = [zone for zone in zones if zone.zone_type in included]
    by_id = {zone.zone_id: zone for zone in usable}
    drop_on_ground = bool(cfg.raw.get("filters", {}).get("drop_on_ground", True))

    for state in states:
        reasons: list[ExitReason] = []
        emitted = False
        if drop_on_ground and state.on_ground:
            reasons.append(ExitReason.ON_GROUND)
        else:
            candidates = [by_id[z] for z in candidate_zone_ids(state, usable, cfg)]
            if not candidates:
                reasons.append(ExitReason.NO_CANDIDATE)
            for zone in candidates:
                containment = check_containment(state, [zone], cfg)
                if not containment.buffered_contained:
                    reasons.append(containment.reason or ExitReason.OUTSIDE_POLYGON)
                    continue
                vertical = vertical_check(state, zone)
                if not vertical.within:
                    reasons.append(vertical.reason or ExitReason.VERTICAL_CLEAR)
                    continue
                activation = is_active(zone, state.timestamp)
                if activation.state is ActivationState.INACTIVE:
                    reasons.append(ExitReason.ZONE_INACTIVE)
                    continue
                emitted = True
                yield build_detection(
                    state=state,
                    zone=zone,
                    containment=containment,
                    vertical=vertical,
                    activation=activation,
                    signals=gather_signals(state, cfg),
                    cfg=cfg,
                )
        if not emitted and exits is not None:
            exits[max(reasons, key=_EXIT_ORDER.index)] += 1
