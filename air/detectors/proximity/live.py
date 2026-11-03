"""Proximity's columns for the live detection table.

The runner (scripts/run_live_detector.py) imports ``extra_columns`` from here
and hands it to ``air.live.persistence.persist``, which fills the shared columns
itself. This module only adds what is specific to proximity: the pair and the
predicted closest approach (db/schema/003_proximity_detections.sql).

No DB access and no detector logic here — it reads facts the detector already
put on the Detection.
"""

from __future__ import annotations

from typing import Any

from contracts import Detection

TABLE = "proximity_detections"
_CPA_EVIDENCE = "predicted_closest_approach"


def extra_columns(detection: Detection) -> dict[str, Any]:
    """Map one proximity Detection to its proximity-only columns.

    ``member_entity_ids`` is both aircraft, sorted, so the same pair always
    looks the same whichever aircraft the detector listed first. The numbers
    come from the ``predicted_closest_approach`` evidence; if it is missing they
    are None (abstain, don't guess).
    """
    members = sorted(e.entity_id for e in detection.entities_involved)
    cpa = next((e.metadata for e in detection.evidence if e.evidence_type == _CPA_EVIDENCE), {})
    return {
        "member_entity_ids": members,
        "predicted_horizontal_nm": cpa.get("predicted_horizontal_nm"),
        "predicted_vertical_ft": cpa.get("predicted_vertical_ft"),
        "t_cpa_seconds": cpa.get("t_cpa_s"),
    }


__all__ = ["TABLE", "extra_columns"]
