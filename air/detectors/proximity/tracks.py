"""Time alignment: put every aircraft's track onto the same 1-second clock.

WHY THIS EXISTS. Aircraft report at irregular moments. If we compare A's
position at 12:00:03 against B's at 12:00:07, B has moved ~half a mile in
those 4 seconds and we invent a conflict that never happened. This is the
single biggest source of phantom detections, so it is step ONE of the
pipeline, not an optimisation.

Input and output are both lists of ``AdsbObservation`` — the interpolated
points are just new observations with made-up (but honest) timestamps.

OWNER: Erik (interpolate_to_grid). group_tracks and align_tracks are done.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta

from air.detectors.proximity.config import ProximityConfig
from air.models.observation import AdsbObservation


def group_tracks(observations: list[AdsbObservation]) -> dict[str, list[AdsbObservation]]:
    """DONE. Bucket observations by aircraft, each bucket sorted by time."""
    tracks: dict[str, list[AdsbObservation]] = {}
    for obs in observations:
        tracks.setdefault(obs.icao24, []).append(obs)
    for track in tracks.values():
        track.sort(key=lambda o: o.observed_at)
    return tracks


def _lerp(a: float | None, b: float | None, frac: float) -> float | None:
    """Linear interpolation; None if either end is missing (abstain, don't guess)."""
    if a is None or b is None:
        return None
    return a + (b - a) * frac


def _lerp_angle(a: float | None, b: float | None, frac: float) -> float | None:
    """Interpolate a compass angle the SHORT way round (350 -> 10 passes 0, not 180)."""
    if a is None or b is None:
        return None
    delta = ((b - a + 180.0) % 360.0) - 180.0
    return (a + delta * frac) % 360.0


def interpolate_to_grid(
    track: list[AdsbObservation],
    step_s: float = 1.0,
    max_gap_s: float = 30.0,
) -> list[AdsbObservation]:
    """Resample one aircraft's track onto whole multiples of ``step_s`` seconds.

    ``track`` is ONE aircraft's observations, already sorted by time (see
    ``group_tracks``). Return a new list with one observation at every grid
    tick between the first and last real report, where a grid tick is a
    timestamp whose seconds-since-epoch is a whole multiple of ``step_s``
    (with step 1.0 that means every :00.000, :01.000, :02.000 ...).

    For each tick, find the real reports immediately before and after it,
    compute ``frac = (tick - before) / (after - before)`` and linearly blend:

        latitude, longitude, altitude_ft, ground_speed_kt, vertical_rate_fpm
            -> plain linear blend (use ``_lerp``)
        track_deg
            -> compass angle, blend the short way round (use ``_lerp_angle``)
        everything else (icao24, callsign, nic, nacp, squawk, receiver_id)
            -> copy from the ``before`` report

    Rules:
      * If ``after - before`` is longer than ``max_gap_s`` the aircraft went
        silent; do NOT invent positions across that gap — skip those ticks.
      * A tick that lands exactly on a real report returns that report's values.
      * An empty or single-point track returns [] (nothing to interpolate).

    Tip: ``dataclasses.replace(before, observed_at=tick, latitude=..., ...)``
    builds the new observation without retyping every field.
    """
    raise NotImplementedError("TODO Erik: see docstring above and the tests")


def align_tracks(
    observations: list[AdsbObservation], cfg: ProximityConfig
) -> dict[datetime, list[AdsbObservation]]:
    """DONE. All aircraft -> {grid tick: [one observation per aircraft at that tick]}.

    This is the shape the rest of the pipeline wants: for each instant, the
    snapshot of everyone in the sky at that exact same instant.
    """
    snapshots: dict[datetime, list[AdsbObservation]] = {}
    for track in group_tracks(observations).values():
        for obs in interpolate_to_grid(track, cfg.grid_step_s, cfg.max_gap_s):
            snapshots.setdefault(obs.observed_at, []).append(obs)
    return dict(sorted(snapshots.items()))


__all__ = ["align_tracks", "group_tracks", "interpolate_to_grid"]
