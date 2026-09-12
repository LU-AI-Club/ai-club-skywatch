"""Domain-agnostic detection model for SENTINEL.

VENDORED, READ-ONLY. Faithful copy of the ``Detection`` half of
sentinel.core.models.detection. Two deliberate trims from the platform file:

- imports repointed to the local ``contracts`` package;
- ``AnalyticCase`` / ``CaseClassification`` removed. Those are maritime
  dark-fleet case types (DARK_FLEET, GRAY_FLEET, ...) that SkyWatch detectors
  never produce — a detector emits a ``Detection``; TCE/CAATS builds the case.

Everything a detector needs to *emit* is here and byte-identical to the
platform: Detection, Evidence, EntityRef, TimeBounds, GeoContext,
SeverityLevel, and the ML attribution records. ``Detection.to_dict()``
produces the same shape the real pipeline consumes. Do not hand-edit; see
contracts/README.md.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from numbers import Real
from typing import Any, Dict, List, Optional, Type, TypeVar, Union, cast
from uuid import UUID, uuid4

from contracts.entity import CrossDomainTag, GeoPosition
from contracts.provenance import ProvenanceRecord


Identifier = Union[str, UUID]
EnumT = TypeVar("EnumT", bound=Enum)


class SeverityLevel(str, Enum):
    """Operational severity for a detection output."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


def _require_non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")


def _validate_optional_text(value: Optional[str], field_name: str) -> None:
    if value is None:
        return
    _require_non_blank(value, field_name)


def _validate_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise ValueError(f"{field_name} must be a datetime")


def _validate_number(value: Optional[float], field_name: str) -> None:
    if value is not None and (isinstance(value, bool) or not isinstance(value, Real)):
        raise ValueError(f"{field_name} must be a number")


def _validate_non_negative(value: Optional[float], field_name: str) -> None:
    _validate_number(value, field_name)
    if value is not None and value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _validate_probability(value: Optional[float], field_name: str) -> None:
    _validate_number(value, field_name)
    if value is not None and not 0.0 <= value <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")


def _validate_finite_number(value: float, field_name: str) -> float:
    _validate_number(value, field_name)
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"{field_name} must be finite")
    return number


def _normalize_identifier(value: Identifier, field_name: str) -> Identifier:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            raise ValueError(f"{field_name} must not be blank")
        return normalized
    raise ValueError(f"{field_name} must be a string or UUID")


def _normalize_enum(enum_type: Type[EnumT], value: EnumT | str, field_name: str) -> EnumT:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        try:
            return enum_type(normalized)
        except ValueError as exc:
            allowed = ", ".join(member.value for member in enum_type)
            raise ValueError(f"{field_name} must be one of: {allowed}") from exc
    raise ValueError(f"{field_name} must be a string or {enum_type.__name__}")


def _serialize(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _serialize(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _serialize(getattr(value, field.name))
            for field in fields(cast(Any, value))
        }
    return value


@dataclass
class EntityRef:
    """Reference to an entity involved in a detection or case."""

    entity_id: Identifier
    entity_type: Optional[str] = None
    domain: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.entity_id = _normalize_identifier(self.entity_id, "entity_id")
        _validate_optional_text(self.entity_type, "entity_type")
        _validate_optional_text(self.domain, "domain")


@dataclass
class Evidence:
    """Evidence item supporting a detection."""

    evidence_type: str
    summary: Optional[str] = None
    source_ref: Optional[str] = None
    observation_id: Optional[Identifier] = None
    entity_id: Optional[Identifier] = None
    confidence: Optional[float] = None
    weight: Optional[float] = None
    timestamp: Optional[datetime] = None
    provenance: Optional[ProvenanceRecord] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence_id: Identifier = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        self.evidence_id = _normalize_identifier(self.evidence_id, "evidence_id")
        _require_non_blank(self.evidence_type, "evidence_type")
        _validate_optional_text(self.summary, "summary")
        _validate_optional_text(self.source_ref, "source_ref")
        if self.observation_id is not None:
            self.observation_id = _normalize_identifier(
                self.observation_id,
                "observation_id",
            )
        if self.entity_id is not None:
            self.entity_id = _normalize_identifier(self.entity_id, "entity_id")
        _validate_probability(self.confidence, "confidence")
        _validate_probability(self.weight, "weight")
        if self.timestamp is not None:
            _validate_datetime(self.timestamp, "timestamp")


@dataclass
class TimeBounds:
    """Temporal extent of a detection or evidence relationship."""

    start_time: datetime
    end_time: Optional[datetime] = None

    def __post_init__(self) -> None:
        _validate_datetime(self.start_time, "start_time")
        if self.end_time is not None:
            _validate_datetime(self.end_time, "end_time")
            if self.end_time < self.start_time:
                raise ValueError("end_time must be greater than or equal to start_time")

    def duration_seconds(self) -> Optional[float]:
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class GeoContext:
    """Geospatial context for a detection output."""

    centroid: Optional[GeoPosition] = None
    geometry: Optional[Dict[str, Any]] = None
    h3_indices: List[str] = field(default_factory=list)
    risk_zone_ids: List[str] = field(default_factory=list)
    distance_meters: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.geometry is not None and not isinstance(self.geometry, dict):
            raise ValueError("geometry must be a dictionary placeholder")
        for index, h3_index in enumerate(self.h3_indices):
            _require_non_blank(h3_index, f"h3_indices[{index}]")
        for index, risk_zone_id in enumerate(self.risk_zone_ids):
            _require_non_blank(risk_zone_id, f"risk_zone_ids[{index}]")
        _validate_non_negative(self.distance_meters, "distance_meters")


@dataclass
class FeatureAttribution:
    """Feature-level model attribution attached to a detector output."""

    feature_name: str
    contribution: float
    direction: Optional[str] = None
    evidence_refs: List[Identifier] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_blank(self.feature_name, "feature_name")
        self.contribution = _validate_finite_number(
            self.contribution,
            "contribution",
        )
        _validate_optional_text(self.direction, "direction")
        self.evidence_refs = [
            _normalize_identifier(ref, f"evidence_refs[{index}]")
            for index, ref in enumerate(self.evidence_refs)
        ]
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


@dataclass
class GraphAttentionAttribution:
    """Graph attention attribution attached to a detector output."""

    source_node: Identifier
    target_node: Identifier
    weight: float
    relationship: Optional[str] = None
    evidence_refs: List[Identifier] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_node = _normalize_identifier(self.source_node, "source_node")
        self.target_node = _normalize_identifier(self.target_node, "target_node")
        _validate_probability(self.weight, "weight")
        self.weight = float(self.weight)
        _validate_optional_text(self.relationship, "relationship")
        self.evidence_refs = [
            _normalize_identifier(ref, f"evidence_refs[{index}]")
            for index, ref in enumerate(self.evidence_refs)
        ]
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


@dataclass
class PredictionIntervalAttribution:
    """Prediction interval or confidence band attached to a detector output."""

    lower_bound: float
    upper_bound: float
    confidence_level: Optional[float] = None
    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.lower_bound = _validate_finite_number(self.lower_bound, "lower_bound")
        self.upper_bound = _validate_finite_number(self.upper_bound, "upper_bound")
        if self.upper_bound < self.lower_bound:
            raise ValueError("upper_bound must be greater than or equal to lower_bound")
        _validate_probability(self.confidence_level, "confidence_level")
        if self.confidence_level is not None:
            self.confidence_level = float(self.confidence_level)
        _validate_optional_text(self.label, "label")
        if not isinstance(self.metadata, dict):
            raise ValueError("metadata must be a dictionary")


def _normalize_attributions(
    values: Sequence[Any],
    expected_type: type,
    field_name: str,
) -> list[Any]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError(f"{field_name} must be a sequence")
    normalized = []
    for index, value in enumerate(values):
        if isinstance(value, expected_type):
            normalized.append(value)
            continue
        if isinstance(value, Mapping):
            try:
                normalized.append(expected_type(**dict(value)))
            except TypeError as exc:
                raise ValueError(
                    f"{field_name}[{index}] must be a {expected_type.__name__}"
                ) from exc
            continue
        raise ValueError(f"{field_name}[{index}] must be a {expected_type.__name__}")
    return normalized


@dataclass
class Detection:
    """Versioned detector output with evidence and provenance."""

    detector_id: str
    detector_version: str
    detection_type: str
    severity: SeverityLevel
    confidence: float
    temporal_bounds: TimeBounds
    provenance: ProvenanceRecord
    entities_involved: List[EntityRef] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
    geospatial_context: GeoContext = field(default_factory=GeoContext)
    tags: List[CrossDomainTag] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    feature_attributions: List[FeatureAttribution] = field(default_factory=list)
    graph_attention_attributions: List[GraphAttentionAttribution] = field(default_factory=list)
    prediction_intervals: List[PredictionIntervalAttribution] = field(default_factory=list)
    trust_assessment: Optional[Dict[str, Any]] = None
    detection_id: Identifier = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        self.detection_id = _normalize_identifier(self.detection_id, "detection_id")
        _require_non_blank(self.detector_id, "detector_id")
        _require_non_blank(self.detector_version, "detector_version")
        _require_non_blank(self.detection_type, "detection_type")
        self.severity = _normalize_enum(SeverityLevel, self.severity, "severity")
        _validate_probability(self.confidence, "confidence")
        if self.temporal_bounds is None:
            raise ValueError("temporal_bounds is required")
        if self.provenance is None:
            raise ValueError("provenance is required")
        if self.geospatial_context is None:
            raise ValueError("geospatial_context is required")
        self.feature_attributions = _normalize_attributions(
            self.feature_attributions,
            FeatureAttribution,
            "feature_attributions",
        )
        self.graph_attention_attributions = _normalize_attributions(
            self.graph_attention_attributions,
            GraphAttentionAttribution,
            "graph_attention_attributions",
        )
        self.prediction_intervals = _normalize_attributions(
            self.prediction_intervals,
            PredictionIntervalAttribution,
            "prediction_intervals",
        )
        if self.trust_assessment is not None:
            self.set_trust_assessment(self.trust_assessment)

    def add_entity(self, entity: EntityRef) -> None:
        if not isinstance(entity, EntityRef):
            raise TypeError("entity must be an instance of EntityRef")
        self.entities_involved.append(entity)

    def add_evidence(self, evidence: Evidence) -> None:
        if not isinstance(evidence, Evidence):
            raise TypeError("evidence must be an instance of Evidence")
        self.evidence.append(evidence)

    def add_tag(self, tag: CrossDomainTag) -> None:
        if not isinstance(tag, CrossDomainTag):
            raise TypeError("tag must be an instance of CrossDomainTag")
        self.tags.append(tag)

    def set_trust_assessment(self, assessment: Dict[str, Any]) -> None:
        if not isinstance(assessment, dict):
            raise ValueError("trust_assessment must be a dictionary placeholder")
        self.trust_assessment = dict(assessment)

    def to_dict(self) -> Dict[str, Any]:
        """Return a serialization-friendly representation of the detection."""

        return cast(Dict[str, Any], _serialize(self))


__all__ = [
    "Detection",
    "EntityRef",
    "Evidence",
    "FeatureAttribution",
    "GeoContext",
    "GraphAttentionAttribution",
    "Identifier",
    "PredictionIntervalAttribution",
    "SeverityLevel",
    "TimeBounds",
]
