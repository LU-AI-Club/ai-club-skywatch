"""Collapse a run of identical rule hits into one finding.

A rule that fires on consecutive pairs fires many times for one piece of
behaviour. On a real hour one aircraft produced twelve separate climb-rate
alerts for a single stretch of flight, and another produced twenty-eight
across rules. Each was true; together they are one thing happening, reported
twelve times.

That matters past tidiness. The alert count is the number the team is judged
on, and an analyst reading a queue has to tell "twelve aircraft misbehaved"
from "one aircraft misbehaved twelve times". Twelve rows say the first.

This groups hits of the same rule on the same aircraft within one segment,
splits them where the aircraft went quiet long enough to call it a separate
episode, and keeps the most extreme hit as the one to report -- the worst
moment is the one worth looking at, and its own measurement is what the
scoring lane should judge. How many hits it stood for, and how long the
episode ran, are recorded on the finding.

Deliberately not done here: treating repetition as corroboration. A finding
that recurs is plausibly stronger evidence than one that does not, but that
is a claim about confidence and belongs with the persistence work, not in a
function whose job is to avoid saying the same thing twice.
"""

from __future__ import annotations

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.records import SpoofingEvent

__all__ = ["consolidate_episodes", "episode_key"]


def episode_key(event: SpoofingEvent) -> tuple:
    """What makes two hits the same ongoing thing rather than two things.

    The same rule, on the same aircraft, inside the same unbroken stretch of
    track. Segment id matters: the detector already split the track where
    the aircraft went quiet, and behaviour either side of a silence is not
    one continuous episode.
    """
    return (
        event.gate,
        tuple(sorted(event.icao24s)),
        event.details.get("segment_id"),
    )


def _extremity(event: SpoofingEvent) -> float:
    """How far past its limit a hit went, for picking the one to report.

    Compared as a ratio rather than a raw value so the choice means the same
    thing for knots and for feet per minute. A hit with nothing measured
    sorts lowest: it is real, but it cannot out-argue one carrying a number.
    """
    if event.measured is None or not event.threshold:
        return 0.0
    return abs(event.measured) / abs(event.threshold)


def consolidate_episodes(
    events: list[SpoofingEvent], cfg: SpoofingConfig
) -> list[SpoofingEvent]:
    """One event per episode, in the order the episodes started.

    Hits are grouped by :func:`episode_key`, then split wherever more than
    ``cfg.episode_gap_s`` separates one hit from the end of the run so far.
    The most extreme hit in each episode is returned, widened to span the
    whole episode and carrying ``episode_hits`` and ``episode_duration_s``.

    An episode of one is returned unchanged apart from those two details, so
    a single finding never looks different for having been through here.
    """
    grouped: dict[tuple, list[SpoofingEvent]] = {}
    for event in events:
        grouped.setdefault(episode_key(event), []).append(event)

    consolidated: list[SpoofingEvent] = []
    for group in grouped.values():
        group.sort(key=lambda e: (e.observed_from, e.observed_to))

        run: list[SpoofingEvent] = []
        run_end = None
        for event in group:
            if run_end is not None and (
                (event.observed_from - run_end).total_seconds() > cfg.episode_gap_s
            ):
                consolidated.append(_merge(run))
                run = []
            run.append(event)
            run_end = event.observed_to if run_end is None else max(run_end, event.observed_to)
        if run:
            consolidated.append(_merge(run))

    consolidated.sort(key=lambda e: (e.observed_from, e.gate))
    return consolidated


def _merge(run: list[SpoofingEvent]) -> SpoofingEvent:
    """The one event that stands for this episode."""
    worst = max(run, key=_extremity)
    started = min(e.observed_from for e in run)
    ended = max(e.observed_to for e in run)

    details = dict(worst.details)
    details["episode_hits"] = len(run)
    details["episode_duration_s"] = round((ended - started).total_seconds(), 3)

    # Everything else comes from the worst hit on purpose: its measurement is
    # what the scoring lane judges, and its position is where to look.
    return SpoofingEvent(
        gate=worst.gate,
        detection_type=worst.detection_type,
        reason=worst.reason,
        icao24s=worst.icao24s,
        observed_from=started,
        observed_to=ended,
        measured=worst.measured,
        threshold=worst.threshold,
        unit=worst.unit,
        latitude=worst.latitude,
        longitude=worst.longitude,
        altitude_ft=worst.altitude_ft,
        features=worst.features,
        details=details,
    )
