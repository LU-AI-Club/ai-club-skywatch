"""air.live — live-integration spine (shared infrastructure).

Three components, one owned by each detector team, that connect the detectors to
the live ADS-B stream. Each component follows its frozen signature. See
docs/live_integration/SPINE_PLAN.md and the per-team guides.

    A  observations_reader.read_window   read a window of observations   (Spoofing)
    B  persistence.persist / dedup_key   upsert detections, run heartbeat (Proximity)
    C  runner.run_live                   the continuous poll loop         (No-Fly-Zone)
"""

from __future__ import annotations

from air.live.observations_reader import read_window
from air.live.persistence import (
    PersistResult,
    dedup_key,
    finish_run,
    persist,
    start_run,
)
from air.live.runner import Detector, run_live

__all__ = [
    "read_window",
    "PersistResult",
    "dedup_key",
    "persist",
    "start_run",
    "finish_run",
    "Detector",
    "run_live",
]
