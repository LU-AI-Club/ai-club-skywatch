"""No-fly-zone's columns for the live detection table.

The runner (scripts/run_live_detector.py) imports ``extra_columns`` from here
and hands it to ``air.live.persistence.persist``, which fills the shared columns
itself. This module only adds what is specific to no-fly-zone: which zone the
incursion was in (db/schema/004_no_fly_zone_detections.sql). ``duration_seconds``
is a generated column, so it is not set here.

No DB access and no detector logic here - it reads facts the detector already
put on the Detection. ``emit.py`` copies the internal Detection's ``extras``
into ``metadata["extras"]``; scoring puts ``zone_id``, ``zone_name`` and
``zone_type`` there.

Inputs / Outputs
----------------
One platform ``contracts.Detection`` in, a dict of the three zone columns out.

Failure causes
--------------
ValueError
    ``zone_id`` or ``zone_type`` is missing. Both columns are NOT NULL, so a
    detection without them cannot be stored; saying which key is missing beats
    a Postgres constraint error. ``zone_name`` may be absent (column is nullable).
"""

from __future__ import annotations

from typing import Any

from contracts import Detection

TABLE = "no_fly_zone_detections"


def extra_columns(detection: Detection) -> dict[str, Any]:
    """Map one no-fly-zone Detection to its no-fly-zone-only columns."""
    extras = (detection.metadata or {}).get("extras") or {}
    missing = [key for key in ("zone_id", "zone_type") if not extras.get(key)]
    if missing:
        raise ValueError(
            f"no-fly-zone detection has no {', '.join(missing)} in metadata['extras']; "
            "scoring.build_detection must set it (see emit.py)."
        )
    return {
        "zone_id": str(extras["zone_id"]),
        "zone_name": extras.get("zone_name") or None,
        "zone_type": str(extras["zone_type"]),
    }


__all__ = ["TABLE", "extra_columns"]
