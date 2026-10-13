"""LEAD-OWNED - converts the internal Detection into the SENTINEL contract.

Why this module exists
----------------------
``types.Detection`` is our internal vocabulary: it carries an
``anomaly_score``, ``limitations`` and ``ExitReason`` context that the stages
reason about. ``contracts.Detection`` is the platform's vendored contract, and
``contracts/__init__.py`` is explicit that emitting the real one is what keeps
Week-11 TCE/CAATS integration "a wiring exercise instead of a rewrite".

Rather than rewrite the stages against the platform contract (which would drag
``contracts`` into every module and break the "import only from types and
config" rule), the conversion happens once, here, at the boundary. Stages stay
pure and testable; the file we hand the platform is the shape it expects.

Field mapping
-------------
===========================  ====================================
internal                     platform
===========================  ====================================
detector_id                  detector_id
detector_version             detector_version
detection_type               detection_type
severity                     severity          (by name)
raw_model_confidence         confidence
anomaly_score                metadata["anomaly_score"]   (*)
entity_ids                   entities_involved[].entity_id
evidence_refs                evidence[].source_ref
explanation_facts            evidence[0].summary + metadata
limitations                  metadata["limitations"]
feature_schema_version       metadata["feature_schema_version"]
baseline_or_model_version    processing_chain[0].transform_version
extras["zone_id"]            geospatial_context.risk_zone_ids
extras (remainder)           metadata["extras"]
===========================  ====================================

(*) The one lossy step. The platform contract has a single probability field,
``confidence``, meaning "how sure are we". Our ``anomaly_score`` means "how
anomalous is this" - a different quantity. Collapsing them would be wrong, so
``confidence`` carries ``raw_model_confidence`` and ``anomaly_score`` rides in
metadata. If the platform later grows a score field, this is the line to move.

Required ``extras`` keys
------------------------
The platform contract requires ``temporal_bounds`` and ``provenance``, neither
of which ``types.Detection`` carries. Stream G must therefore put these into
``extras`` when it builds the Detection:

``observed_at``
    The AircraftState timestamp - a tz-aware datetime or ISO-8601 string.
``source_row_id``
    Provenance back to the raw record.
``lat`` / ``lon``
    Position, for the geospatial centroid.

Optional: ``altitude_ft``, ``zone_id``, ``penetration_nm``, ``dwell_sec``.

Inputs / Outputs
----------------
Takes one internal :class:`Detection`, returns one platform
:class:`PlatformDetection`.

Failure causes
--------------
ValueError
    A required ``extras`` key is missing or unusable. Raised loudly rather than
    defaulted: a Detection with a fabricated timestamp is worse than no
    Detection, because it looks authoritative.

Notes
-----
The platform ``Detection`` is a plain (mutable) dataclass and assigns itself a
random ``detection_id`` UUID. So the output is neither frozen nor
deterministic - tests must ignore ``detection_id`` or pass one explicitly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from contracts import Detection as PlatformDetection
from contracts import (
    EntityRef,
    Evidence,
    GeoContext,
    GeoPosition,
    ProcessingStep,
    ProvenanceRecord,
    SeverityLevel,
    TimeBounds,
)

from .types import Detection

DOMAIN = "air"
SOURCE_SYSTEM = "skywatch"
STEP_NAME = "no_fly_zone_detection"


def _require(extras: dict[str, Any], key: str) -> Any:
    """Read a required extras key, or say exactly which one is missing."""
    if key not in extras or extras[key] is None:
        raise ValueError(
            f"Detection.extras is missing required key {key!r}. "
            f"Stream G must populate it - see emit.py for the full list."
        )
    return extras[key]


def _as_datetime(value: Any, field_name: str) -> datetime:
    """Accept a datetime or an ISO-8601 string; reject anything else."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field_name} is not ISO-8601: {value!r}") from exc
    raise ValueError(f"{field_name} must be a datetime or ISO-8601 string")


def to_platform_detection(detection: Detection) -> PlatformDetection:
    """Convert an internal Detection into the vendored SENTINEL contract."""
    extras = dict(detection.extras)

    observed_at = _as_datetime(_require(extras, "observed_at"), "observed_at")
    source_row_id = str(_require(extras, "source_row_id"))
    lat = float(_require(extras, "lat"))
    lon = float(_require(extras, "lon"))
    altitude_ft = extras.get("altitude_ft")
    zone_id = extras.get("zone_id")

    provenance = ProvenanceRecord(
        source_system=SOURCE_SYSTEM,
        raw_source_ref=source_row_id,
        processing_chain=(
            ProcessingStep(
                timestamp=observed_at,
                step_name=STEP_NAME,
                transform_id=detection.detector_id,
                # Pins the rules version AND the airspace publication cycle.
                transform_version=detection.baseline_or_model_version,
            ),
        ),
    )

    # One Evidence per reference. The first carries the explanation text so an
    # analyst reading the platform record sees the reasoning, not just an id.
    summary = " ".join(detection.explanation_facts) or None
    evidence = [
        Evidence(
            evidence_type=detection.detection_type,
            summary=summary if index == 0 else None,
            source_ref=ref,
            confidence=detection.raw_model_confidence,
            timestamp=observed_at,
        )
        for index, ref in enumerate(detection.evidence_refs)
    ]

    penetration_nm = extras.get("penetration_nm")
    geo = GeoContext(
        centroid=GeoPosition(
            latitude=lat,
            longitude=lon,
            altitude=float(altitude_ft) if altitude_ft is not None else None,
        ),
        risk_zone_ids=[str(zone_id)] if zone_id else [],
        # Contract requires non-negative; penetration is a depth, never signed.
        distance_meters=(
            abs(float(penetration_nm)) * 1852.0 if penetration_nm is not None else None
        ),
    )

    return PlatformDetection(
        detector_id=detection.detector_id,
        detector_version=detection.detector_version,
        detection_type=detection.detection_type,
        severity=SeverityLevel(detection.severity.value),
        confidence=detection.raw_model_confidence,
        temporal_bounds=TimeBounds(start_time=observed_at, end_time=observed_at),
        provenance=provenance,
        entities_involved=[
            EntityRef(entity_id=eid, entity_type="aircraft", domain=DOMAIN)
            for eid in detection.entity_ids
        ],
        evidence=evidence,
        geospatial_context=geo,
        metadata={
            # No first-class home in the platform contract - see module docstring.
            "anomaly_score": detection.anomaly_score,
            "feature_schema_version": detection.feature_schema_version,
            "baseline_or_model_version": detection.baseline_or_model_version,
            "explanation_facts": list(detection.explanation_facts),
            "limitations": list(detection.limitations),
            "extras": extras,
        },
    )


__all__ = ["to_platform_detection"]
