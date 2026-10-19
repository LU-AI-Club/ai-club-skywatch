"""LEAD-OWNED - wires the stages together. No detection logic lives here.

The pipeline, in order, with the :class:`ExitReason` recorded when a state
leaves without a detection:

    H3 coarse filter      -> NO_CANDIDATE
    exact containment     -> OUTSIDE_POLYGON
    vertical check        -> VERTICAL_CLEAR
    activation            -> ZONE_INACTIVE
    context signals       -> (never exits; only lowers the score)
    score                 -> a per-report Detection
    episode grouping      -> one Detection per incursion (logic/episodes.py)

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
An iterator of :class:`Detection`, one per incursion episode (an aircraft in a
zone from entry to exit). Pass ``per_report=True`` for the raw per-report
detections instead, which is what episodes are built from. Exit reasons are
counted per report, not returned, so the CLI can report why states dropped
out - a detector that emits nothing and cannot say why is untestable.

Episode mode sorts the states by aircraft and time first (the recorded CSV is
not perfectly time-ordered), so it holds them all in memory; per-report mode
streams.

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

# Stages are referenced through their modules (not ``from x import fn``) so a
# test can monkeypatch one stage without touching the others.
from ..config import Config
from ..geo import altitude, containment, zone_index
from ..types import (
    ActivationState,
    AircraftState,
    AirspaceZone,
    ContextSignal,
    Detection,
    ExitReason,
    ReportResult,
)
from . import activation, context, episodes, scoring

# When one state is tested against several zones and none fires, the state is
# counted once, under the stage it got furthest through. This is bookkeeping
# for the exit histogram, not a detection decision.
_EXIT_DEPTH: dict[ExitReason, int] = {
    ExitReason.ON_GROUND: 0,
    ExitReason.NO_CANDIDATE: 1,
    ExitReason.OUTSIDE_POLYGON: 2,
    ExitReason.BAD_INPUT: 3,
    ExitReason.VERTICAL_CLEAR: 3,
    ExitReason.ZONE_INACTIVE: 4,
}


def run(
    states: Iterable[AircraftState],
    zones: list[AirspaceZone],
    cfg: Config,
    *,
    exit_counts: Counter[ExitReason] | None = None,
    per_report: bool = False,
) -> Iterator[Detection]:
    """Run the full pipeline over ``states``, yielding one Detection per episode.

    Pass a :class:`collections.Counter` as ``exit_counts`` to have every state
    that produced no detection counted under its :class:`ExitReason`. The
    counter fills as the iterator is consumed. ``per_report=True`` skips
    episode grouping and yields every per-report detection.
    """
    counts: Counter[ExitReason] = exit_counts if exit_counts is not None else Counter()
    zones_by_id = {zone.zone_id: zone for zone in zones}
    drop_on_ground = bool(cfg.raw.get("filters", {}).get("drop_on_ground", True))

    def evaluate(state: AircraftState) -> tuple[Detection, ...]:
        return _evaluate(state, zones, zones_by_id, cfg, counts, drop_on_ground)

    if per_report:
        for state in states:
            yield from evaluate(state)
        return

    reports = evaluate_reports(states, zones, cfg, exit_counts=counts)
    yield from episodes.group_episodes(reports, cfg)


def evaluate_reports(
    states: Iterable[AircraftState],
    zones: list[AirspaceZone],
    cfg: Config,
    *,
    exit_counts: Counter[ExitReason] | None = None,
) -> Iterator[ReportResult]:
    """Every stage except episode grouping, as the input episodes need.

    Sorts ``states`` by aircraft and time, then yields one :class:`ReportResult`
    per state. :func:`run` passes these to ``episodes.group_episodes``; the
    adapter passes each runner window's results to one long-lived
    ``episodes.EpisodeTracker`` so episodes survive window edges.
    """
    counts: Counter[ExitReason] = exit_counts if exit_counts is not None else Counter()
    zones_by_id = {zone.zone_id: zone for zone in zones}
    drop_on_ground = bool(cfg.raw.get("filters", {}).get("drop_on_ground", True))
    ordered = sorted(states, key=lambda s: (s.icao24.strip().lower(), s.timestamp))
    for state in ordered:
        fired = _evaluate(state, zones, zones_by_id, cfg, counts, drop_on_ground)
        yield ReportResult(state.icao24, state.timestamp, fired)


def _evaluate(
    state: AircraftState,
    zones: list[AirspaceZone],
    zones_by_id: dict[str, AirspaceZone],
    cfg: Config,
    counts: Counter[ExitReason],
    drop_on_ground: bool,
) -> tuple[Detection, ...]:
    """Every per-report Detection for one state; counts its exit if none fire."""
    if drop_on_ground and state.on_ground:
        counts[ExitReason.ON_GROUND] += 1
        return ()

    candidate_ids = zone_index.candidate_zone_ids(state, zones, cfg)
    candidates = [zones_by_id[zid] for zid in candidate_ids if zid in zones_by_id]
    if not candidates:
        counts[ExitReason.NO_CANDIDATE] += 1
        return ()

    fired: list[Detection] = []
    deepest = ExitReason.NO_CANDIDATE
    signals: list[ContextSignal] | None = None  # gathered once, only if needed

    # One zone at a time, so penetration_nm and the activation result in
    # each Detection refer to that zone and nothing else.
    for zone in candidates:
        horizontal = containment.check_containment(state, [zone], cfg)
        if not (horizontal.contained or horizontal.buffered_contained):
            deepest = _deeper(deepest, horizontal.reason or ExitReason.OUTSIDE_POLYGON)
            continue

        vertical = altitude.vertical_check(state, zone)
        if not vertical.within:
            deepest = _deeper(deepest, vertical.reason or ExitReason.VERTICAL_CLEAR)
            continue

        live = activation.is_active(zone, state.timestamp)
        if live.state is ActivationState.INACTIVE:
            deepest = _deeper(deepest, ExitReason.ZONE_INACTIVE)
            continue
        # UNKNOWN continues on purpose: scoring caps its severity.

        if signals is None:
            signals = context.gather_signals(state, cfg)
        fired.append(
            scoring.build_detection(state, zone, horizontal, vertical, live, signals, cfg)
        )

    if not fired:
        counts[deepest] += 1
    return tuple(fired)


def _deeper(current: ExitReason, candidate: ExitReason) -> ExitReason:
    """Keep whichever exit reason got further down the pipeline."""
    return candidate if _EXIT_DEPTH[candidate] > _EXIT_DEPTH[current] else current
