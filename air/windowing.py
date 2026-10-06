"""Time-windowing for replaying observations into detectors.

**Shared enabling infrastructure** (Tech-Lead owned), not detector logic. It
turns a flat stream of ``AdsbObservation`` into time-ordered *windows* and feeds
each window to detectors. Detectors stay pure functions over a
``list[AdsbObservation]`` — this module decides *which* observations make up each
window; a detector decides what to do with them.

Why windows, and why epoch-anchored
------------------------------------
Two of the three SkyWatch detectors are stateful across a short span of time:
proximity compares aircraft that are airborne *at the same moment*, and spoofing
compares an aircraft's *consecutive* positions. Feeding one observation at a time
would starve them, so we hand each detector a time slice wide enough to work on.

Window boundaries are anchored to the **epoch**, not to the first row in the
file: a window is ``[k*step, k*step + window)`` for integer ``k``. This mirrors
the maritime M-003 detector's fixed time buckets
(``FLOOR(epoch / bucket_width)``). The payoff is that *the same real timestamp
always lands in the same window*, no matter which file or run produced it — so a
live, repeating run over a rolling "last N minutes" window is reproducible and
idempotent, exactly like the one-shot file replay. Anchoring at "first row"
would shift every boundary when the input changed.

Tumbling vs sliding
-------------------
* ``step == window`` (default): **tumbling** — non-overlapping partitions. No
  observation appears in two windows, so detections are emitted once. Simplest.
* ``step <  window``: **sliding** — overlapping windows. Catches an event that
  straddles a tumbling boundary (a spoof jump or an encounter spanning the
  edge), at the cost of the same detection appearing in more than one window.
  Pair it with ``detection_dedup_key`` / ``run_detectors(dedup=True)``.

The production equivalent of the overlap problem is solved by a wider *context*
window plus an idempotent upsert keyed on a stable id (see the maritime
proximity detector). In this no-database replay we approximate that with dedup.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Iterator, Protocol

from air.models.observation import AdsbObservation


class _Detector(Protocol):
    """Anything the runner can drive: the ``detect_observations`` convention."""

    detector_id: str

    def detect_observations(self, observations: list[AdsbObservation]) -> list[Any]:
        ...


def iter_windows(
    observations: Iterable[AdsbObservation],
    window_s: float,
    step_s: float | None = None,
) -> Iterator[list[AdsbObservation]]:
    """Yield time-ordered windows of observations, epoch-anchored.

    Parameters
    ----------
    observations:
        Any iterable of ``AdsbObservation`` (unsorted is fine — sorted here).
    window_s:
        Window width in seconds. Each window is ``[s, s + window_s)`` (half-open:
        an observation exactly at ``s + window_s`` belongs to the next window).
    step_s:
        How far the window start advances each time. Defaults to ``window_s``
        (tumbling). A smaller value gives overlapping (sliding) windows.

    Windows with no observations (time gaps) are skipped; the final partial
    window is included. Runs in O(n log n) for the sort plus O(n + windows) for
    the sweep, via two monotonic pointers — no per-window rescan of the data.
    """
    if window_s <= 0:
        raise ValueError("window_s must be > 0")
    if step_s is None:
        step_s = window_s
    if step_s <= 0:
        raise ValueError("step_s must be > 0")

    obs = sorted(observations, key=lambda o: o.observed_at)
    if not obs:
        return
    epochs = [o.observed_at.timestamp() for o in obs]
    n = len(obs)
    min_t, max_t = epochs[0], epochs[-1]

    # Floor the first window start to the step grid so boundaries are anchored
    # to the epoch, identical across files/runs.
    start = math.floor(min_t / step_s) * step_s
    lo = 0  # first index with epoch >= start  (monotonic non-decreasing)
    hi = 0  # first index with epoch >= start + window_s (monotonic)
    while start <= max_t:
        window_end = start + window_s
        while lo < n and epochs[lo] < start:
            lo += 1
        if hi < lo:
            hi = lo
        while hi < n and epochs[hi] < window_end:
            hi += 1
        if hi > lo:
            yield obs[lo:hi]
        start += step_s


def detection_dedup_key(detection: Any) -> tuple:
    """A stable identity for a detection, for collapsing duplicates produced by
    overlapping (sliding) windows.

    Keyed on the fields that identify *the same finding about the same entities
    at the same time*: detector id/version, detection type, the sorted set of
    involved entity ids, and the start of the temporal bounds. Deliberately
    ignores volatile fields (confidence, evidence ordering, the random
    ``detection_id``) so the same event seen in two windows collapses to one.
    """
    entities = tuple(
        sorted(getattr(e, "entity_id", "") for e in (getattr(detection, "entities_involved", None) or []))
    )
    bounds = getattr(detection, "temporal_bounds", None)
    start = getattr(bounds, "start_time", None)
    start_key = start.isoformat() if start is not None else None
    return (
        getattr(detection, "detector_id", None),
        getattr(detection, "detector_version", None),
        getattr(detection, "detection_type", None),
        entities,
        start_key,
    )


def run_detectors(
    windows: Iterable[list[AdsbObservation]],
    detectors: list[_Detector],
    *,
    dedup: bool = False,
) -> Iterator[Any]:
    """Drive each detector over each window, yielding Detections in order.

    Each detector gets the *whole* window and groups internally as it needs
    (per-aircraft for spoofing, co-temporal for proximity, per-point for
    no-fly-zone). With ``dedup=True`` a detection whose ``detection_dedup_key``
    has already been seen is skipped — use it for sliding windows.
    """
    seen: set[tuple] = set()
    for window in windows:
        for detector in detectors:
            for detection in detector.detect_observations(window):
                if dedup:
                    key = detection_dedup_key(detection)
                    if key in seen:
                        continue
                    seen.add(key)
                yield detection


__all__ = ["iter_windows", "run_detectors", "detection_dedup_key"]
