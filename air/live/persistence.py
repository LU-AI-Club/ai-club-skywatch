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
import re
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

    ``conn`` is a psycopg 3 connection (or anything with the same
    ``cursor()`` / ``execute(sql, params)`` / ``fetchone()`` shape). This function
    does NOT commit: the caller owns the transaction, so a whole run can be
    committed or rolled back together.

    A detection with no involved entity or no start time can't fill the
    ``NOT NULL`` columns; it is counted as ``skipped`` rather than guessed at.
    """
    _check_identifier(table)
    result = PersistResult()
    with conn.cursor() as cur:
        for detection in detections:
            row = _base_row(detection, run_id)
            if row is None:
                result.skipped += 1
                continue
            if extra_columns is not None:
                extra = extra_columns(detection)
                clash = set(extra) & set(row)
                if clash:
                    raise ValueError(
                        f"extra_columns may not override shared columns: {sorted(clash)}"
                    )
                row.update(extra)
            cur.execute(*_upsert_sql(table, row))
            inserted = cur.fetchone()[0]
            if inserted:
                result.inserted += 1
            else:
                result.updated += 1
    return result


# Shared columns stored as JSONB (sent as JSON text and cast in SQL).
_JSONB_COLUMNS = frozenset(
    {
        "entities_involved", "evidence", "geospatial_context", "provenance",
        "tags", "metadata", "raw_detection",
    }
)
# Kept from the first write when a dedup_key is seen again. Everything else is
# overwritten with the newest version of the finding.
_KEEP_ON_UPDATE = frozenset({"detection_id", "dedup_key", "first_detected_at", "created_at"})
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def _check_identifier(name: str) -> None:
    """Table and column names can't be SQL parameters, so only allow plain names."""
    if not _IDENTIFIER.match(name):
        raise ValueError(f"not a plain SQL identifier: {name!r}")


def _base_row(detection: Detection, run_id: str | None) -> dict[str, Any] | None:
    """The shared columns from ``Detection.to_dict()``, or None if it can't fill them."""
    d = detection.to_dict()
    entities = d.get("entities_involved") or []
    bounds = d.get("temporal_bounds") or {}
    if not entities or not entities[0].get("entity_id") or not bounds.get("start_time"):
        return None
    centroid = (d.get("geospatial_context") or {}).get("centroid") or {}
    return {
        "detection_id": d["detection_id"],
        "dedup_key": dedup_key(detection),
        "detector_id": d["detector_id"],
        "detector_version": d["detector_version"],
        "detection_type": d["detection_type"],
        "severity": d["severity"],
        "confidence": d["confidence"],
        "entity_id": entities[0]["entity_id"],
        "entities_involved": entities,
        "temporal_bounds_start": bounds["start_time"],
        "temporal_bounds_end": bounds.get("end_time"),
        "latitude": centroid.get("latitude"),
        "longitude": centroid.get("longitude"),
        "evidence": d.get("evidence") or [],
        "geospatial_context": d.get("geospatial_context") or {},
        "provenance": d.get("provenance") or {},
        "tags": d.get("tags") or [],
        "metadata": d.get("metadata") or {},
        "raw_detection": d,
        "detection_run_id": run_id,
    }


def _upsert_sql(table: str, row: dict[str, Any]) -> tuple[str, list[Any]]:
    """``INSERT ... ON CONFLICT (dedup_key) DO UPDATE ... RETURNING inserted``.

    ``RETURNING (xmax = 0)`` is the standard Postgres way to tell the two paths
    apart: a freshly inserted row has no deleting transaction (xmax 0), an
    updated one does.
    """
    columns = list(row)
    for col in columns:
        _check_identifier(col)
    placeholders = ["%s::jsonb" if c in _JSONB_COLUMNS else "%s" for c in columns]
    params = [json.dumps(row[c], default=str) if c in _JSONB_COLUMNS else row[c] for c in columns]
    updates = [f"{c} = EXCLUDED.{c}" for c in columns if c not in _KEEP_ON_UPDATE]
    updates += ["last_detected_at = now()", "updated_at = now()"]
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join(placeholders)}) "
        f"ON CONFLICT (dedup_key) DO UPDATE SET {', '.join(updates)} "
        "RETURNING (xmax = 0) AS inserted"
    )
    return sql, params


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
