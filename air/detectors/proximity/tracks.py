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
    # Work in whole microseconds since epoch so tick maths is exact integer
    # arithmetic -- float seconds (~1.8e9) would drift off :00.000.
    # datetime cannot represent anything finer than 1 us, so a step that is
    # not a whole number of microseconds has no honest grid: refuse it rather
    # than silently resample onto a different one.
    step_us_float = step_s * 1_000_000
    if not math.isfinite(step_us_float):
        raise ValueError(f"step_s must be a positive whole number of microseconds, got {step_s!r}")
    step_us = round(step_us_float)
    # abs_tol is a float-precision tolerance, not a detection threshold.
    if step_us <= 0 or not math.isclose(step_us_float, step_us, rel_tol=0.0, abs_tol=1e-6):
        raise ValueError(f"step_s must be a positive whole number of microseconds, got {step_s!r}")

    if math.isnan(max_gap_s) or max_gap_s < 0:
        raise ValueError(f"max_gap_s must be non-negative and not NaN, got {max_gap_s!r}")

    if len(track) < 2:
        return []

    epoch = datetime(1970, 1, 1, tzinfo=track[0].observed_at.tzinfo)
    one_us = timedelta(microseconds=1)

    out: list[AdsbObservation] = []
    last_k: int | None = None  # index of the last tick emitted, to avoid duplicates
    for before, after in zip(track, track[1:]):
        b_us = (before.observed_at - epoch) // one_us
        a_us = (after.observed_at - epoch) // one_us
        span_us = a_us - b_us
        # Across a silence (or between duplicate timestamps) only ticks that
        # land exactly on a real report are emitted; nothing is invented.
        # Compare in seconds: scaling max_gap_s to microseconds can put an
        # exact boundary just below the integer span (e.g. 1.001 seconds).
        can_blend = span_us > 0 and span_us / 1_000_000 <= max_gap_s

        if can_blend:
            ks = range(-(-b_us // step_us), a_us // step_us + 1)  # ceil .. floor
        else:
            ks = [t // step_us for t in (b_us, a_us) if t % step_us == 0]

        for k in ks:
            if last_k is not None and k <= last_k:
                continue  # already emitted by the previous segment
            tick_us = k * step_us
            if tick_us == b_us:
                obs = before  # exact hit: the real report, untouched
            elif tick_us == a_us:
                obs = after
            else:
                frac = (tick_us - b_us) / span_us
                obs = replace(
                    before,
                    observed_at=epoch + timedelta(microseconds=tick_us),
                    latitude=_lerp(before.latitude, after.latitude, frac),
                    longitude=_lerp(before.longitude, after.longitude, frac),
                    altitude_ft=_lerp(before.altitude_ft, after.altitude_ft, frac),
                    ground_speed_kt=_lerp(before.ground_speed_kt, after.ground_speed_kt, frac),
                    vertical_rate_fpm=_lerp(before.vertical_rate_fpm, after.vertical_rate_fpm, frac),
                    track_deg=_lerp_angle(before.track_deg, after.track_deg, frac),
                )
            out.append(obs)
            last_k = k
    return out


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
