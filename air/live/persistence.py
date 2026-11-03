"""Spine component B — persist Detections to a detector's table, idempotently.

OWNER: Proximity team (see docs/live_integration/TEAM_PROXIMITY.md).

Fills the shared columns of any air detection table generically from
``Detection.to_dict()`` and upserts on ``dedup_key`` so re-processing an
overlapping window updates a row in place instead of duplicating it. Each
detector supplies only its extra columns via the ``extra_columns`` hook. Also
owns the shared ``detector_runs`` heartbeat.

``PersistResult`` and ``dedup_key`` are implemented here (everyone needs them
real). ``persist``, ``start_run`` and ``finish_run`` are stubs for the Proximity
team to fill in. The signatures are FROZEN — the runner (C) and the other teams
import them; announce any change.

See docs/live_integration/DETECTION_TABLE_COLUMNS.md for the shared columns these
fill, and air/windowing.py for ``detection_dedup_key``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from air.windowing import detection_dedup_key
from contracts import Detection


@dataclass
class PersistResult:
    """Row counts from one ``persist`` call."""

    inserted: int = 0
    updated: int = 0
    skipped: int = 0


def dedup_key(detection: Detection) -> str:
    """Stable string identity for a detection — the upsert conflict target.

    Wraps ``air.windowing.detection_dedup_key`` (which keys on detector
    id/version, detection type, the sorted involved entity ids, and the
    temporal start) and serializes it to a deterministic string so it can be a
    ``TEXT UNIQUE`` column. Two detections that are "the same finding about the
    same entities at the same time" produce the same key, so the overlap a
    rolling window creates collapses to one row.
    """
    return json.dumps(detection_dedup_key(detection), default=str, separators=(",", ":"))


def persist(
    conn: Any,
    table: str,
    detections: Iterable[Detection],
    *,
    run_id: str | None = None,
    extra_columns: Callable[[Detection], dict[str, Any]] | None = None,
) -> PersistResult:
    """Upsert ``detections`` into ``table`` and return row counts.

    Behavior the implementation must provide
    ----------------------------------------
    * Fill the shared base columns from ``Detection.to_dict()`` (see
      DETECTION_TABLE_COLUMNS.md): ids, type, severity, confidence, entity_id,
      entities_involved, temporal bounds, lat/lon, evidence, geospatial_context,
      provenance, tags, metadata, raw_detection, and ``dedup_key`` (this module).
    * Merge the per-detector columns from ``extra_columns(detection)`` when given.
    * ``INSERT ... ON CONFLICT (dedup_key) DO UPDATE ..., updated_at = now()``:
      a second write of the same finding updates in place and bumps
      ``last_detected_at``; it is never a duplicate row.
    * Stamp ``detection_run_id`` with ``run_id`` when provided.
    * Return a ``PersistResult`` with inserted / updated / skipped counts.
    """
    raise NotImplementedError("Spine B: Proximity team — see docs/live_integration/TEAM_PROXIMITY.md")


def start_run(
    conn: Any,
    detector_id: str,
    detector_version: str,
    *,
    window: tuple[datetime, datetime] | None = None,
) -> str:
    """Insert a RUNNING row in ``detector_runs`` and return its ``run_id``."""
    raise NotImplementedError("Spine B: Proximity team — see docs/live_integration/TEAM_PROXIMITY.md")


def finish_run(
    conn: Any,
    run_id: str,
    *,
    status: str,
    counts: dict[str, Any],
) -> None:
    """Update the ``detector_runs`` row to SUCCESS/FAILED with its counts."""
    raise NotImplementedError("Spine B: Proximity team — see docs/live_integration/TEAM_PROXIMITY.md")


__all__ = ["PersistResult", "dedup_key", "persist", "start_run", "finish_run"]
