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


# How a detection wants to be deduplicated, declared in its own
# ``metadata["dedup_scope"]``. A detector that says nothing gets "event",
# which is the behaviour this function has always had.
DEDUP_SCOPE_EVENT = "event"
DEDUP_SCOPE_ENTITY = "entity"
DEDUP_SCOPES = (DEDUP_SCOPE_EVENT, DEDUP_SCOPE_ENTITY)


def detection_dedup_key(detection: Any) -> tuple:
    """A stable identity for a detection, for collapsing duplicates produced by
    overlapping (sliding) windows.

    Keyed on the fields that identify *the same finding about the same
    entities*: detector id/version, detection type, and the sorted set of
    involved entity ids. Volatile fields -- confidence, evidence ordering, the
    random ``detection_id`` -- are deliberately ignored, so the same finding
    seen in two windows collapses to one.

    Whether the time belongs in that identity depends on what the finding *is*,
    and only the detector knows. It declares this in
    ``metadata["dedup_scope"]``:

    ``"event"`` (the default, and the behaviour before this existed)
        The finding is a thing that happened at a moment: a pair of reports
        that disagree, an encounter, a zone entry. ``temporal_bounds.start_time``
        is part of its identity, and two of them about one aircraft at
        different times are two findings.

        **This requires the detector to anchor ``start_time`` to the finding
        itself, not to the window it was evaluated in.** A pair-based rule gets
        this for free, because the pair's own timestamps do not move. A
        computed instant needs rounding -- see the CPA anchoring in
        ``air/detectors/proximity/detector.py``, which rounds to the second so
        every window agrees.

    ``"entity"``
        The finding is a condition the entity is *in*: degraded navigation
        integrity, a callsign that does not match its registry block, an
        address two transmitters appear to share. There is no instant it
        happened at; it holds over whatever history the window contained, so
        its start slides forward with the window and is not identity-bearing.
        Keyed without the time, and recency is carried by the table's
        ``last_detected_at`` instead.

    Getting this wrong is not a cosmetic problem. Spoofing runs a 3600 s window
    stepping 300 s, so a state-like finding keyed on a sliding start produced a
    fresh key every tick: 82 rows for 62 findings on one capture, growing
    without bound for as long as the runner ran. The upsert cannot help, because
    the keys differ.

    An unrecognised scope raises rather than guessing -- a typo silently
    disabling deduplication is exactly the failure above.
    """
    entities = tuple(
        sorted(getattr(e, "entity_id", "") for e in (getattr(detection, "entities_involved", None) or []))
    )

    metadata = getattr(detection, "metadata", None) or {}
    scope = DEDUP_SCOPE_EVENT
    if hasattr(metadata, "get"):
        scope = metadata.get("dedup_scope", DEDUP_SCOPE_EVENT)
    if scope not in DEDUP_SCOPES:
        raise ValueError(
            f"unknown dedup_scope {scope!r}; expected one of {DEDUP_SCOPES}"
        )

    start_key = None
    if scope == DEDUP_SCOPE_EVENT:
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
    has already been seen is skipped — use it for sliding windows. After the
    last window, any detector with a ``flush()`` method is flushed.
    """
    seen: set[tuple] = set()

    def fresh(detections: Iterable[Any]) -> Iterator[Any]:
        for detection in detections:
            if dedup:
                key = detection_dedup_key(detection)
                if key in seen:
                    continue
                seen.add(key)
            yield detection

    for window in windows:
        for detector in detectors:
            yield from fresh(detector.detect_observations(window))
    # End of stream: detectors that hold state across windows (NFZ keeps open
    # incursion episodes) expose an optional flush() for whatever is still open.
    for detector in detectors:
        flush = getattr(detector, "flush", None)
        if callable(flush):
            yield from fresh(flush())


__all__ = ["iter_windows", "run_detectors", "detection_dedup_key"]
