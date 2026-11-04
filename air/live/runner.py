"""Spine component C — run one detector continuously on the live stream.

OWNER: No-Fly-Zone team (see docs/live_integration/TEAM_NO_FLY_ZONE.md).

Reads a rolling window via component A (``observations_reader.read_window``),
runs the detector, and persists via component B (``persistence.persist``), on a
timer. One harness, parameterized per detector — the other teams do not write
their own loop; they supply the parameters.

The signature below is FROZEN. This runner uses A and B through their frozen
interfaces, which lets it work with their implementations as they land.
"""

from __future__ import annotations

import logging
import math
import signal
import threading
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Protocol, runtime_checkable

from air.live import observations_reader, persistence
from air.models.observation import AdsbObservation
from contracts import Detection

logger = logging.getLogger(__name__)


def _connect(dsn: str) -> Any:
    """Open one database connection; psycopg is an optional runtime extra."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "The live runner requires psycopg; install the 'db' optional dependencies."
        ) from exc
    return psycopg.connect(dsn)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_cursor(conn: Any, detector_id: str) -> datetime | None:
    """Restore the most recent successfully completed window boundary."""
    row = conn.execute(
        """
        SELECT MAX(window_end)
        FROM public.detector_runs
        WHERE detector_id = %s AND status = 'SUCCESS'
        """,
        (detector_id,),
    ).fetchone()
    return row[0] if row and row[0] is not None else None


def _persist_failed_run(
    dsn: str,
    run_id: str,
    counts: dict[str, Any],
    error: Exception,
) -> str | None:
    """Try to mark a started heartbeat failed in a fresh transaction."""
    try:
        with _connect(dsn) as conn:
            persistence.finish_run(
                conn,
                run_id,
                status="FAILED",
                counts={
                    **{
                        key: value
                        for key, value in counts.items()
                        if key != "latest_observed_at"
                    },
                    "error": str(error)[:2000],
                },
            )
        return None
    except Exception as heartbeat_error:
        return f"{type(heartbeat_error).__name__}: {heartbeat_error}"


def _result_counts(result: Any) -> dict[str, int]:
    return {
        name: int(getattr(result, name, 0))
        for name in ("inserted", "updated", "skipped")
    }


def _log_tick(
    *,
    detector_id: str,
    status: str,
    started: float,
    window: tuple[datetime, datetime] | None,
    counts: dict[str, Any],
    error: Exception | None = None,
    heartbeat_error: str | None = None,
) -> None:
    fields: dict[str, Any] = {
        "event": "live_detector_tick",
        "detector_id": detector_id,
        "tick_status": status,
        "duration_seconds": round(monotonic() - started, 3),
        "window_start": window[0].isoformat() if window else None,
        "window_end": window[1].isoformat() if window else None,
        **{
            key: value.isoformat() if isinstance(value, datetime) else value
            for key, value in counts.items()
        },
    }
    if window is not None and counts.get("latest_observed_at") is not None:
        fields["lag_seconds"] = max(
            0.0, (window[1] - counts["latest_observed_at"]).total_seconds()
        )
    else:
        fields["lag_seconds"] = None
    if error is not None:
        fields["error_type"] = type(error).__name__
        fields["error"] = str(error)
    if heartbeat_error is not None:
        fields["heartbeat_error"] = heartbeat_error

    if status == "SUCCESS":
        logger.info("live detector tick", extra=fields)
    else:
        logger.error("live detector tick", extra=fields)


def _install_sigterm_handler(stop: threading.Event) -> Any:
    if threading.current_thread() is not threading.main_thread():
        return None
    previous = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, lambda _signum, _frame: stop.set())
    return previous


def _restore_sigterm_handler(previous: Any) -> None:
    if previous is not None:
        signal.signal(signal.SIGTERM, previous)


@runtime_checkable
class Detector(Protocol):
    """What the runner needs from a detector.

    Every SkyWatch detector satisfies this. A detector MAY also expose
    ``flush() -> list[Detection]`` for state held across windows (no-fly-zone
    keeps incursion episodes open); the runner calls it when present.
    """

    detector_id: str

    def detect_observations(self, observations: list[AdsbObservation]) -> list[Detection]:
        ...


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
        Rolling lookback ``W``; each tick reads one window ending at its
        successful watermark, with a ``window_s`` lookback.
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

    A failed tick is logged and isolated; successful ``window_end`` watermarks
    are restored from ``detector_runs`` on the next tick or process restart.
    """
    if not all(math.isfinite(value) for value in (window_s, step_s, poll_interval_s)):
        raise ValueError("window_s, step_s, and poll_interval_s must be finite")
    if window_s <= 0 or step_s <= 0 or poll_interval_s <= 0:
        raise ValueError("window_s, step_s, and poll_interval_s must be positive")
    if step_s > window_s:
        raise ValueError("step_s must not exceed window_s")

    detector_id = detector.detector_id
    detector_version = getattr(detector, "detector_version", "unknown")
    stop = threading.Event()
    previous_sigterm = _install_sigterm_handler(stop)
    pending: list[Detection] = []

    def run_tick(*, flush: bool, read: bool = True) -> None:
        started = monotonic()
        counts: dict[str, Any] = {
            "read_count": 0,
            "detection_count": 0,
            "inserted": 0,
            "updated": 0,
            "skipped": 0,
            "latest_observed_at": None,
        }
        error: Exception | None = None
        heartbeat_error: str | None = None
        run_id: str | None = None
        window: tuple[datetime, datetime] | None = None

        try:
            with _connect(dsn) as conn:
                if read:
                    cursor = _load_cursor(conn, detector_id)
                    now = _utcnow()
                    if cursor is None:
                        window_end = now
                    else:
                        window_end = max(
                            cursor,
                            min(now, cursor + timedelta(seconds=step_s)),
                        )
                    window = (
                        window_end - timedelta(seconds=window_s),
                        window_end,
                    )
                run_id = persistence.start_run(
                    conn,
                    detector_id,
                    detector_version,
                    window=window,
                )
                conn.commit()

                if read:
                    observations = observations_reader.read_window(
                        conn,
                        start=window[0],
                        end=window[1],
                        domain=domain,
                    )
                else:
                    observations = []
                counts["read_count"] = len(observations)
                if observations:
                    counts["latest_observed_at"] = max(
                        observation.observed_at for observation in observations
                    )

                detections = list(detector.detect_observations(observations)) if read else []
                flush_method = getattr(detector, "flush", None)
                if flush and callable(flush_method):
                    detections.extend(flush_method())
                counts["detection_count"] = len(detections)
                pending.extend(detections)

                if pending:
                    result = persistence.persist(
                        conn,
                        table,
                        pending,
                        run_id=run_id,
                        extra_columns=extra_columns,
                    )
                    counts.update(_result_counts(result))
                finish_run_counts = {
                    key: value
                    for key, value in counts.items()
                    if key != "latest_observed_at"
                }
                persistence.finish_run(
                    conn,
                    run_id,
                    status="SUCCESS",
                    counts=finish_run_counts,
                )
                pending.clear()
        except Exception as tick_error:
            error = tick_error
            if run_id is not None:
                heartbeat_error = _persist_failed_run(dsn, run_id, counts, tick_error)

        _log_tick(
            detector_id=detector_id,
            status="ERROR" if error is not None else "SUCCESS",
            started=started,
            window=window,
            counts=counts,
            error=error,
            heartbeat_error=heartbeat_error,
        )

    try:
        while True:
            run_tick(flush=once)
            if once or stop.is_set():
                break
            if stop.wait(poll_interval_s):
                break

        if not once and stop.is_set() and callable(getattr(detector, "flush", None)):
            run_tick(flush=True, read=False)
    finally:
        _restore_sigterm_handler(previous_sigterm)


__all__ = ["Detector", "run_live"]
