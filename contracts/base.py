"""Base detector contracts for the SENTINEL detection framework.

VENDORED, READ-ONLY. Faithful copy of sentinel.detection.base with the single
import repointed to the local ``contracts`` package. Every SkyWatch detector
subclasses ``BaseDetector`` and returns the ``Detection`` model, exactly as the
maritime detectors do. See contracts/README.md.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from numbers import Real
from typing import Any
from uuid import UUID

from contracts.detection import Detection, EntityRef, Identifier


ObservationRecord = Mapping[str, Any]


class DetectorImplementationType(str, Enum):
    """Implementation family used by TCE governance gates.

    The Bias gate uses this typed signal to decide applicability; detector
    names are intentionally not part of the governance contract.
    """

    RULE_BASED = "RULE_BASED"
    MACHINE_LEARNING = "MACHINE_LEARNING"


def _require_non_blank(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a sequence of strings")
    return tuple(
        _require_non_blank(item, f"{field_name}[{index}]")
        for index, item in enumerate(value)
    )


def _mapping_tuple(value: object, field_name: str) -> tuple[ObservationRecord, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a sequence of mappings")
    records: list[ObservationRecord] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"{field_name}[{index}] must be a mapping")
        records.append(dict(item))
    return tuple(records)


def _entity_ref_tuple(value: object, field_name: str) -> tuple[EntityRef, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{field_name} must be a sequence of EntityRef objects")
    refs: list[EntityRef] = []
    for index, item in enumerate(value):
        if not isinstance(item, EntityRef):
            raise TypeError(f"{field_name}[{index}] must be an EntityRef")
        refs.append(item)
    return tuple(refs)


def _mapping_copy(value: object, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return dict(value)


def _normalize_optional_identifier(value: object, field_name: str) -> Identifier | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    return _require_non_blank(value, field_name)


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_blank(value, field_name)


def _normalize_implementation_type(
    value: object,
    field_name: str,
) -> DetectorImplementationType:
    if isinstance(value, DetectorImplementationType):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        try:
            return DetectorImplementationType(normalized)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in DetectorImplementationType)
            raise ValueError(f"{field_name} must be one of: {allowed}") from exc
    raise ValueError(
        f"{field_name} must be a string or DetectorImplementationType"
    )


@dataclass(frozen=True, slots=True)
class DetectorMetadata:
    """Typed detector metadata consumed by TCE hard gates."""

    implementation_type: DetectorImplementationType | str
    detector_id: str | None = None
    detector_version: str | None = None
    model_id: str | None = None
    model_version: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "implementation_type",
            _normalize_implementation_type(
                self.implementation_type,
                "implementation_type",
            ),
        )
        object.__setattr__(self, "detector_id", _optional_text(self.detector_id, "detector_id"))
        object.__setattr__(self, "detector_version", _optional_text(self.detector_version, "detector_version"))
        object.__setattr__(self, "model_id", _optional_text(self.model_id, "model_id"))
        object.__setattr__(self, "model_version", _optional_text(self.model_version, "model_version"))


@dataclass(frozen=True, slots=True)
class DataRequirements:
    """Data contract a detector needs before it can run."""

    observation_types: Sequence[str] = ()
    source_names: Sequence[str] = ()
    auxiliary_data_keys: Sequence[str] = ()
    lookback_hours: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observation_types",
            _string_tuple(self.observation_types, "observation_types"),
        )
        object.__setattr__(
            self,
            "source_names",
            _string_tuple(self.source_names, "source_names"),
        )
        object.__setattr__(
            self,
            "auxiliary_data_keys",
            _string_tuple(self.auxiliary_data_keys, "auxiliary_data_keys"),
        )
        if self.lookback_hours is not None:
            if isinstance(self.lookback_hours, bool) or not isinstance(
                self.lookback_hours,
                Real,
            ):
                raise ValueError("lookback_hours must be a number")
            if self.lookback_hours <= 0:
                raise ValueError("lookback_hours must be greater than 0")
            object.__setattr__(self, "lookback_hours", float(self.lookback_hours))


@dataclass(frozen=True, slots=True)
class DetectionContext:
    """Runtime input passed to a detector.

    The context stays intentionally small. Detector stories can place
    source-specific records in observations or auxiliary_data without changing
    the base detector contract.
    """

    observations: Sequence[ObservationRecord] = ()
    entity_refs: Sequence[EntityRef] = ()
    auxiliary_data: Mapping[str, Any] = field(default_factory=dict)
    parameters: Mapping[str, Any] = field(default_factory=dict)
    run_id: Identifier | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observations",
            _mapping_tuple(self.observations, "observations"),
        )
        object.__setattr__(
            self,
            "entity_refs",
            _entity_ref_tuple(self.entity_refs, "entity_refs"),
        )
        object.__setattr__(
            self,
            "auxiliary_data",
            _mapping_copy(self.auxiliary_data, "auxiliary_data"),
        )
        object.__setattr__(
            self,
            "parameters",
            _mapping_copy(self.parameters, "parameters"),
        )
        object.__setattr__(
            self,
            "run_id",
            _normalize_optional_identifier(self.run_id, "run_id"),
        )


class BaseDetector(ABC):
    """Abstract base for composable, versioned detection algorithms."""

    detector_id: str = ""
    detector_version: str = ""
    domain: str = ""
    implementation_type: DetectorImplementationType = (
        DetectorImplementationType.RULE_BASED
    )

    def __init__(self) -> None:
        self.validate_metadata()

    @classmethod
    def validate_metadata(cls) -> None:
        """Validate detector metadata declared on the detector class."""

        _require_non_blank(cls.detector_id, "detector_id")
        _require_non_blank(cls.detector_version, "detector_version")
        _require_non_blank(cls.domain, "domain")
        _normalize_implementation_type(cls.implementation_type, "implementation_type")

    @abstractmethod
    def detect(self, context: DetectionContext) -> list[Detection]:
        """Run detection logic against provided context."""
        raise NotImplementedError

    @abstractmethod
    def get_required_data(self) -> DataRequirements:
        """Declare what data this detector needs."""
        raise NotImplementedError


__all__ = [
    "BaseDetector",
    "DataRequirements",
    "DetectionContext",
    "DetectorImplementationType",
    "DetectorMetadata",
    "ObservationRecord",
]
