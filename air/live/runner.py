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

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from air.live.observations_reader import read_window
from air.live.persistence import finish_run, persist, start_run
from air.models.observation import AdsbObservation
from contracts import Detection

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
    keeps incursion episodes open); the runner calls it when present.
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


def _tick(
    *,
    detector: Detector,
    table: str,
    dsn: str,
    window_s: float,
    step_s: float,
    extra_columns: Callable[[Detection], dict[str, Any]] | None,
    domain: str,
) -> None:
    """Run one read -> detect -> persist pass over the next rolling window.

    Opens a connection, advances the cursor by at most one step, reads that
    window via component A (``read_window``), runs the detector (plus
    ``flush()`` if it exposes one), and persists via component B (``persist``).
    On success the detections, the advanced cursor, and the SUCCESS heartbeat
    commit together; on failure the window's writes roll back — so the cursor is
    not advanced and the window is retried next tick — and the run is marked
    FAILED. ``psycopg`` is imported here so ``air.live`` stays importable without
    the ``db`` extra.
    """
    import psycopg

    detector_id = detector.detector_id
    detector_version = getattr(detector, "detector_version", "") or "unknown"

    with psycopg.connect(dsn) as conn:
        cursor_at = _load_cursor(conn, detector_id)
        start, end = _window_bounds(
            cursor_at=cursor_at,
            now=datetime.now(UTC),
            window_s=window_s,
            step_s=step_s,
        )
        run_id = start_run(conn, detector_id, detector_version, window=(start, end))
        try:
            observations = read_window(conn, start=start, end=end, domain=domain)
            detections = list(detector.detect_observations(observations))
            flush = getattr(detector, "flush", None)
            if callable(flush):
                detections.extend(flush())
            result = persist(conn, table, detections, run_id=run_id, extra_columns=extra_columns)
            _save_cursor(conn, detector_id, end)
            finish_run(
                conn,
                run_id,
                status="SUCCESS",
                counts={
                    "observations": len(observations),
                    "detections": len(detections),
                    "inserted": result.inserted,
                    "updated": result.updated,
                    "skipped": result.skipped,
                },
            )
        except Exception as exc:
            conn.rollback()
            finish_run(conn, run_id, status="FAILED", counts={"error": str(exc)})
            raise


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
    * Call ``detector.flush()`` when present so a finding spanning a window edge
      is one row, not two.
    * Be resilient: isolate errors per tick, log one structured line per tick,
      shut down cleanly on SIGTERM.
    """
    if window_s <= 0:
        raise ValueError("window_s must be greater than zero")
    if step_s <= 0:
        raise ValueError("step_s must be greater than zero")
    if step_s > window_s:
        raise ValueError("step_s must not exceed window_s")
    if poll_interval_s <= 0:
        raise ValueError("poll_interval_s must be greater than zero")

    while True:
        _tick(
            detector=detector,
            table=table,
            dsn=dsn,
            window_s=window_s,
            step_s=step_s,
            extra_columns=extra_columns,
            domain=domain,
        )
        if once:
            return
        time.sleep(poll_interval_s)

__all__ = ["Detector", "run_live"]
