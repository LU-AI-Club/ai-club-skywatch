"""Provenance models for SENTINEL lineage and trust records.

VENDORED, READ-ONLY COPY of sentinel.core.models.provenance from the
xenith-sentinel-platform repo. Do not hand-edit — see contracts/README.md for
why this is copied here and how to re-sync it. Keeping this identical to the
platform is what lets a SkyWatch detection flow into the real TCE/CAATS
pipeline in Week 11 without a rewrite.

These models are canonical provenance primitives used by observations,
entities, detections, and Trust/Confidence Engine outputs. They are passive
contracts only; hash verification and lineage scoring belong to later TCE
components.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence, Set as AbstractSet
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

__all__ = [
    "ProcessingStep",
    "ProvenanceChain",
    "ProvenanceRecord",
    "QualityAssessment",
]


Identifier = str | UUID
_SHA256_HEX_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class _FrozenDict(dict[str, Any]):
    """Small immutable dict that remains compatible with dataclasses.asdict."""

    def __setitem__(self, key: str, value: Any) -> None:
        raise TypeError("mapping is immutable")

    def __delitem__(self, key: str) -> None:
        raise TypeError("mapping is immutable")

    def clear(self) -> None:
        raise TypeError("mapping is immutable")

    def pop(self, key: str, default: Any = None) -> Any:
        raise TypeError("mapping is immutable")

    def popitem(self) -> tuple[str, Any]:
        raise TypeError("mapping is immutable")

    def setdefault(self, key: str, default: Any = None) -> Any:
        raise TypeError("mapping is immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:
        raise TypeError("mapping is immutable")

    def __ior__(self, other: Any) -> "_FrozenDict":
        raise TypeError("mapping is immutable")


def _require_non_blank(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value.strip()


def _validate_datetime(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"{field_name} must be a datetime or ISO-8601 string"
            ) from exc
    else:
        raise TypeError(f"{field_name} must be a datetime or ISO-8601 string")

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _validate_optional_datetime(value: Any, field_name: str) -> datetime | None:
    if value is None:
        return None
    return _validate_datetime(value, field_name)


def _validate_probability(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a number")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field_name} must be between 0.0 and 1.0")
    return number


def _validate_optional_probability(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _validate_probability(value, field_name)


def _validate_optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _normalize_optional_identifier(value: Any, field_name: str) -> Identifier | None:
    if value is None:
        return None
    return _normalize_identifier(value, field_name)


def _normalize_identifier(value: Any, field_name: str) -> Identifier:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str):
        return _require_non_blank(value, field_name)
    raise TypeError(f"{field_name} must be a string or UUID")


def _identifier_tuple(value: Any, field_name: str) -> tuple[Identifier, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(
        _normalize_identifier(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence")
    return tuple(
        _require_non_blank(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _FrozenDict(
            {key: _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, (str, bytes)):
        return value
    if isinstance(value, (list, tuple)) or isinstance(value, AbstractSet):
        return tuple(_freeze_value(item) for item in value)
    return value


def _frozen_dict(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return _freeze_value(value)


def _validate_content_hash(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    normalized = _require_non_blank(value, field_name)
    if not _SHA256_HEX_RE.fullmatch(normalized):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex string")
    return normalized.lower()


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """Provenance-level data quality metadata."""

    completeness: float | None = None
    accuracy: float | None = None
    timeliness: float | None = None
    consistency: float | None = None
    integrity: float | None = None
    confidence: float | None = None
    assessed_at: datetime | None = None
    assessor: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "completeness",
            "accuracy",
            "timeliness",
            "consistency",
            "integrity",
            "confidence",
        ):
            object.__setattr__(
                self,
                field_name,
                _validate_optional_probability(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "assessed_at",
            _validate_optional_datetime(self.assessed_at, "assessed_at"),
        )
        if self.assessor is not None:
            object.__setattr__(
                self, "assessor", _require_non_blank(self.assessor, "assessor")
            )
        if self.notes is not None:
            object.__setattr__(self, "notes", _require_non_blank(self.notes, "notes"))


@dataclass(frozen=True, slots=True)
class ProcessingStep:
    timestamp: datetime
    step_name: str
    step_id: Identifier | None = None
    transform_id: str | None = None
    transform_version: str | None = None
    processor: str | None = None
    node_id: str | None = None
    input_refs: tuple[str, ...] = ()
    output_refs: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    execution_duration_ms: int | None = None
    output_summary: str | None = None
    quality_assessment: QualityAssessment | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            _validate_datetime(self.timestamp, "timestamp"),
        )
        object.__setattr__(
            self,
            "step_name",
            _require_non_blank(self.step_name, "step_name"),
        )
        object.__setattr__(
            self,
            "step_id",
            _normalize_optional_identifier(self.step_id, "step_id"),
        )
        for field_name in (
            "transform_id",
            "transform_version",
            "processor",
            "node_id",
            "output_summary",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_non_blank(value, field_name),
                )
        object.__setattr__(self, "input_refs", _string_tuple(self.input_refs, "input_refs"))
        object.__setattr__(
            self,
            "output_refs",
            _string_tuple(self.output_refs, "output_refs"),
        )
        object.__setattr__(
            self,
            "parameters",
            _frozen_dict(self.parameters, "parameters"),
        )
        object.__setattr__(
            self,
            "execution_duration_ms",
            _validate_optional_non_negative_int(
                self.execution_duration_ms,
                "execution_duration_ms",
            ),
        )
        if self.quality_assessment is not None and not isinstance(
            self.quality_assessment, QualityAssessment
        ):
            raise TypeError("quality_assessment must be a QualityAssessment")


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    source_system: str
    processing_chain: tuple[ProcessingStep, ...] = ()
    raw_source_ref: str | None = None
    record_id: Identifier | None = None
    source_feed: str | None = None
    source_timestamp: datetime | None = None
    ingestion_timestamp: datetime | None = None
    source_record_id: str | None = None
    content_hash: str | None = None
    quality_assessment: QualityAssessment | None = None
    classification: str | None = None
    handling_caveats: tuple[str, ...] = ()
    retention_policy: str | None = None
    parent_records: tuple[Identifier, ...] = ()
    derived_records: tuple[Identifier, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_system",
            _require_non_blank(self.source_system, "source_system"),
        )
        if isinstance(self.processing_chain, (str, bytes)) or not isinstance(
            self.processing_chain,
            Sequence,
        ):
            raise TypeError("processing_chain must be a sequence")
        processing_chain = tuple(self.processing_chain)
        for step in processing_chain:
            if not isinstance(step, ProcessingStep):
                raise TypeError(
                    "all items in processing_chain must be ProcessingStep instances"
                )
        object.__setattr__(self, "processing_chain", processing_chain)

        for field_name in (
            "raw_source_ref",
            "source_feed",
            "source_record_id",
            "classification",
            "retention_policy",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    _require_non_blank(value, field_name),
                )

        object.__setattr__(
            self,
            "record_id",
            _normalize_optional_identifier(self.record_id, "record_id"),
        )
        object.__setattr__(
            self,
            "source_timestamp",
            _validate_optional_datetime(self.source_timestamp, "source_timestamp"),
        )
        object.__setattr__(
            self,
            "ingestion_timestamp",
            _validate_optional_datetime(self.ingestion_timestamp, "ingestion_timestamp"),
        )
        object.__setattr__(
            self,
            "content_hash",
            _validate_content_hash(self.content_hash, "content_hash"),
        )
        if self.quality_assessment is not None and not isinstance(
            self.quality_assessment, QualityAssessment
        ):
            raise TypeError("quality_assessment must be a QualityAssessment")
        object.__setattr__(
            self,
            "handling_caveats",
            _string_tuple(self.handling_caveats, "handling_caveats"),
        )
        object.__setattr__(
            self,
            "parent_records",
            _identifier_tuple(self.parent_records, "parent_records"),
        )
        object.__setattr__(
            self,
            "derived_records",
            _identifier_tuple(self.derived_records, "derived_records"),
        )
        object.__setattr__(self, "metadata", _frozen_dict(self.metadata, "metadata"))


@dataclass(frozen=True, slots=True)
class ProvenanceChain:
    records: tuple[ProvenanceRecord, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.records, (str, bytes)) or not isinstance(
            self.records,
            Sequence,
        ):
            raise TypeError("records must be a sequence")
        records = tuple(self.records)
        for record in records:
            if not isinstance(record, ProvenanceRecord):
                raise TypeError("all items in records must be ProvenanceRecord instances")
        object.__setattr__(self, "records", records)
