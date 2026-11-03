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

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from air.models.observation import AdsbObservation
from contracts import Detection


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
    * Cursor/watermark: track the latest ``observed_at`` processed; read via
      ``observations_reader.read_window``; survive restarts.
    * Pass detections to ``persistence.persist`` (which dedups on ``dedup_key``);
      wrap each run in ``persistence.start_run`` / ``finish_run``.
    * Call ``detector.flush()`` when present so a finding spanning a window edge
      is one row, not two.
    * Be resilient: isolate errors per tick, log one structured line per tick,
      shut down cleanly on SIGTERM.
    """
    raise NotImplementedError("Spine C: No-Fly-Zone team — see docs/live_integration/TEAM_NO_FLY_ZONE.md")


__all__ = ["Detector", "run_live"]
