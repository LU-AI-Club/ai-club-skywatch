"""Spine component C — run one detector continuously on the live stream.

OWNER: No-Fly-Zone team (see docs/live_integration/TEAM_NO_FLY_ZONE.md).

Reads a rolling window via component A (``observations_reader.read_window``),
runs the detector, and persists via component B (``persistence.persist``), on a
timer. One harness, parameterized per detector — the other teams do not write
their own loop; they supply the parameters.

The signature below is FROZEN. The body is a stub for the No-Fly-Zone team. C
depends on A and B, so it is written against their frozen signatures/stubs and
integrates once they land.
"""

from __future__ import annotations

import functools
import logging
import signal
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from air.live.observations_reader import read_window
from air.live.persistence import finish_run, persist, start_run
from air.models.observation import AdsbObservation
from contracts import Detection

_log = logging.getLogger(__name__)

# Back-off after a failed tick: poll_interval_s doubled per consecutive
# failure, capped here, so a down database is not hammered every few seconds.
_MAX_BACKOFF_S = 300.0

_CURSOR_SELECT = """
SELECT cursor_at
FROM public.detector_cursors
WHERE detector_id = %s
"""

_CURSOR_UPSERT = """
INSERT INTO public.detector_cursors (detector_id, cursor_at)
VALUES (%s, %s)
ON CONFLICT (detector_id) DO UPDATE
SET cursor_at = GREATEST(public.detector_cursors.cursor_at, EXCLUDED.cursor_at),
    updated_at = now()
"""


@runtime_checkable
class Detector(Protocol):
    """What the runner needs from a detector.

    Every SkyWatch detector satisfies this. A detector MAY also expose
    ``flush() -> list[Detection]`` for state held across windows (no-fly-zone
    keeps incursion episodes open). The runner calls it only at the end of a
    stream - a ``once`` run, or a clean shutdown - never between ticks of the
    continuous loop, where it would close every open finding and split it
    across rows.
    """

    detector_id: str

    def detect_observations(self, observations: list[AdsbObservation]) -> list[Detection]:
        ...


def _load_cursor(conn: Any, detector_id: str) -> datetime | None:
    """Load the end time of the detector's latest successfully processed window."""
    with conn.cursor() as cursor:
        cursor.execute(_CURSOR_SELECT, (detector_id,))
        row = cursor.fetchone()
    if row is None:
        return None

    cursor_at = row[0]
    if not isinstance(cursor_at, datetime):
        raise TypeError("detector cursor must be returned as a datetime")
    if cursor_at.tzinfo is None:
        raise ValueError("detector cursor must be timezone-aware")
    return cursor_at.astimezone(UTC)


def _save_cursor(conn: Any, detector_id: str, cursor_at: datetime) -> None:
    """Save a successful window end without allowing a stale runner to rewind it."""
    if cursor_at.tzinfo is None:
        raise ValueError("detector cursor must be timezone-aware")
    with conn.cursor() as cursor:
        cursor.execute(
            _CURSOR_UPSERT,
            (detector_id, cursor_at.astimezone(UTC)),
        )


def _window_bounds(
    *,
    cursor_at: datetime | None,
    now: datetime,
    window_s: float,
    step_s: float,
) -> tuple[datetime, datetime]:
    """Return the next bounded rolling window and advance by at most one step."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    latest = now.astimezone(UTC)
    if cursor_at is None:
        end = latest
    elif cursor_at.tzinfo is None:
        raise ValueError("detector cursor must be timezone-aware")
    else:
        previous_end = cursor_at.astimezone(UTC)
        end = min(latest, previous_end + timedelta(seconds=step_s))
    return end - timedelta(seconds=window_s), end


@dataclass(frozen=True)
class TickResult:
    """What one successful tick did: its window, counts, and how far behind it is."""

    start: datetime
    end: datetime
    lag_s: float  # now - window end; > 0 means the cursor is still catching up
    counts: dict[str, int]


def _tick(
    *,
    detector: Detector,
    table: str,
    dsn: str,
    window_s: float,
    step_s: float,
    extra_columns: Callable[[Detection], dict[str, Any]] | None,
    domain: str,
    flush: bool,
    pending: list[Detection] | None = None,
) -> TickResult:
    """Run one read -> detect -> persist pass over the next rolling window.

    Opens a connection, advances the cursor by at most one step, reads that
    window via component A (``read_window``), runs the detector (plus
    ``flush()`` if it exposes one and ``flush`` is true - the last tick of a
    stream), and persists via component B (``persist``).
    On success the detections, the advanced cursor, and the SUCCESS heartbeat
    commit together; on failure the window's writes roll back — so the cursor is
    not advanced and the window is retried next tick — and the run is marked
    FAILED. ``psycopg`` is imported here so ``air.live`` stays importable without
    the ``db`` extra.

    ``pending`` carries detections a failed tick produced but could not store.
    The detector has already moved past them (its state is kept across ticks),
    so re-reading the window would not produce them again; they are persisted
    with the next tick instead. Persisting is a ``dedup_key`` upsert, so a
    detection stored twice is still one row.
    """
    import psycopg

    detector_id = detector.detector_id
    detector_version = getattr(detector, "detector_version", "") or "unknown"

    with psycopg.connect(dsn) as conn:
        cursor_at = _load_cursor(conn, detector_id)
        now = datetime.now(UTC)
        start, end = _window_bounds(
            cursor_at=cursor_at,
            now=now,
            window_s=window_s,
            step_s=step_s,
        )
        run_id = start_run(conn, detector_id, detector_version, window=(start, end))
        try:
            detections: list[Detection] = list(pending or [])
            observations = read_window(conn, start=start, end=end, domain=domain)
            detections.extend(detector.detect_observations(observations))
            # Only at the end of a stream. Between ticks the detector must keep
            # its state: NFZ's flush() closes every open incursion, so flushing
            # each tick would end it and restart it as a new row next tick.
            detector_flush = getattr(detector, "flush", None)
            if flush and callable(detector_flush):
                detections.extend(detector_flush())
            result = persist(conn, table, detections, run_id=run_id, extra_columns=extra_columns)
            _save_cursor(conn, detector_id, end)
            counts = {
                "observations": len(observations),
                "detections": len(detections),
                "inserted": result.inserted,
                "updated": result.updated,
                "skipped": result.skipped,
            }
            finish_run(conn, run_id, status="SUCCESS", counts=counts)
            if pending is not None:
                pending.clear()
        except Exception as exc:
            conn.rollback()
            if pending is not None and "detections" in locals():
                pending[:] = detections  # keep for the next tick; see docstring
            finish_run(conn, run_id, status="FAILED", counts={"error": str(exc)})
            raise
    return TickResult(start=start, end=end, lag_s=(now - end).total_seconds(), counts=counts)


def run_live(
    *,
    detector: Detector,
    table: str,
    dsn: str,
    window_s: float,
    step_s: float,
    poll_interval_s: float,
    extra_columns: Callable[[Detection], dict[str, Any]] | None = None,
    domain: str = "air",
    once: bool = False,
) -> None:
    """Run ``detector`` against the live ``observations`` stream.

    Parameters
    ----------
    detector:
        The detector to run (``detect_observations``; optional ``flush``).
    table:
        The detector's detection table to persist into.
    dsn:
        Postgres connection string.
    window_s:
        Rolling lookback ``W``; each tick reads ``[cursor - window_s, now]``.
    step_s:
        How far the cursor advances each tick (overlap = ``window_s - step_s``).
    poll_interval_s:
        Sleep between ticks.
    extra_columns:
        Per-detector column hook, passed through to ``persistence.persist``.
    domain:
        Observation domain to read (``"air"``).
    once:
        Run a single tick and return — used by the end-to-end test and CI.

    Behavior the implementation must provide
    ----------------------------------------
    * Cursor/watermark: track the latest successful window end; read via
      ``observations_reader.read_window``; survive restarts.
    * Pass detections to ``persistence.persist`` (which dedups on ``dedup_key``);
      wrap each run in ``persistence.start_run`` / ``finish_run``.
    * Keep one detector instance across ticks so a finding spanning a window
      edge is one row, not two; call ``detector.flush()`` (when present) only
      when the stream ends, i.e. on a ``once`` run.
    * Be resilient: isolate errors per tick (back off, keep the detector and
      any unsaved detections), log one structured line per tick, shut down
      cleanly on SIGTERM (finish the tick, flush, exit).
    * Catch up: sleep only ``poll_interval_s - lag``, so a runner that fell
      behind (restart, slow tick) runs windows back to back until current.
    """
    if window_s <= 0:
        raise ValueError("window_s must be greater than zero")
    if step_s <= 0:
        raise ValueError("step_s must be greater than zero")
    if step_s > window_s:
        raise ValueError("step_s must not exceed window_s")
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be greater than zero")

    tick = functools.partial(
        _tick, detector=detector, table=table, dsn=dsn, window_s=window_s, step_s=step_s,
        extra_columns=extra_columns, domain=domain,
    )
    detector_id = getattr(detector, "detector_id", "?")
    pending: list[Detection] = []
    failures = 0
    with _StopSignal() as stop:
        while not stop.requested:
            started = time.monotonic()
            try:
                result = tick(flush=once, pending=pending)
            except Exception:
                if once:
                    raise
                # One bad tick must not kill the runner: the detector instance,
                # and with it NFZ's open incursions, has to survive a DB hiccup.
                failures += 1
                cap = max(_MAX_BACKOFF_S, poll_interval_s)
                backoff = min(poll_interval_s * 2 ** (failures - 1), cap)
                _log.exception(
                    "tick detector=%s status=FAILED consecutive_failures=%d pending=%d "
                    "retry_in_s=%.0f",
                    detector_id, failures, len(pending), backoff,
                )
                stop.sleep(backoff)
                continue
            failures = 0
            _log_tick(detector_id, result, time.monotonic() - started)
            if once:
                return
            # Sleep only the part of the interval the cursor is not already
            # behind by. Sleeping the full interval after every tick lost the
            # tick's own run time each time, so the window drifted further
            # behind real time forever and never caught up after a restart.
            stop.sleep(max(0.0, poll_interval_s - result.lag_s))
        _final_flush(detector, tick, pending, detector_id)


def _log_tick(detector_id: str, result: TickResult, duration_s: float) -> None:
    """The one structured line per tick SPINE_PLAN.md asks for."""
    c = result.counts
    _log.info(
        "tick detector=%s status=SUCCESS window_end=%s lag_s=%.1f duration_s=%.2f "
        "observations=%d detections=%d inserted=%d updated=%d skipped=%d",
        detector_id, result.end.isoformat(timespec="seconds"), result.lag_s, duration_s,
        c["observations"], c["detections"], c["inserted"], c["updated"], c["skipped"],
    )


def _final_flush(
    detector: Detector,
    tick: Callable[..., TickResult],
    pending: list[Detection],
    detector_id: str,
) -> None:
    """On shutdown, close what the detector still holds open.

    Shutting down is the end of the stream. Without this, NFZ's open incursions
    stay OPEN in the table forever: after a restart the detector starts empty
    and an aircraft still inside a zone gets a new row with a new start time.
    """
    _log.info("runner detector=%s stopping", detector_id)
    if not callable(getattr(detector, "flush", None)) and not pending:
        return
    try:
        result = tick(flush=True, pending=pending)
        _log_tick(detector_id, result, 0.0)
    except Exception:  # noqa: BLE001 -- shutting down; log it and exit cleanly
        _log.exception(
            "runner detector=%s final flush failed; open findings stay OPEN", detector_id
        )


class _Shutdown(Exception):
    """Raised by the signal handler only while sleeping, to end the sleep at once."""


class _StopSignal:
    """SIGTERM/SIGINT: finish the current tick, close open findings, then stop.

    In a container the runner is PID 1, and Linux ignores SIGTERM for PID 1
    unless a handler is installed, so ``docker compose down`` used to wait its
    10 s grace period and then SIGKILL the runner, mid-tick. A tick is never
    interrupted (its transaction stays whole); a sleep is.
    """

    def __init__(self) -> None:
        self.requested = False
        self._sleeping = False
        self._previous: dict[int, Any] = {}

    def _handle(self, signum: int, _frame: object) -> None:
        self.requested = True
        if self._sleeping:
            raise _Shutdown

    def __enter__(self) -> _StopSignal:
        if threading.current_thread() is threading.main_thread():
            for sig in (signal.SIGTERM, signal.SIGINT):
                self._previous[sig] = signal.getsignal(sig)
                signal.signal(sig, self._handle)
        return self

    def __exit__(self, *_exc: object) -> None:
        for sig, handler in self._previous.items():
            signal.signal(sig, handler)

    def sleep(self, seconds: float) -> None:
        if self.requested or seconds <= 0:
            return
        self._sleeping = True
        try:
            time.sleep(seconds)
        except _Shutdown:
            pass
        finally:
            self._sleeping = False

__all__ = ["Detector", "TickResult", "run_live"]
