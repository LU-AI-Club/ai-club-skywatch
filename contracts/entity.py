"""Domain-agnostic entity primitives needed by the Detection contract.

VENDORED, READ-ONLY. This is a faithful *subset* of the platform's entity /
observation models — only the two types the ``Detection`` contract references:

- ``GeoPosition`` (copied from sentinel.core.models.observation)
- ``CrossDomainTag`` (copied from sentinel.core.models.entity)

The full platform entity model (Vessel, Aircraft, ObservedEntity, ...) is
intentionally NOT copied here: SkyWatch detectors only need to *emit*
detections, not assemble entities. See contracts/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ObservationValidationError(ValueError):
    """Raised when a position model violates the evidence contract."""


def _require_non_blank(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservationValidationError(f"{field_name} must be a non-blank string")
    return value.strip()


def _validate_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ObservationValidationError(f"{field_name} must be a number")
    return float(value)


def _validate_optional_number(value: Any, field_name: str) -> float | None:
    if value is None:
        return None
    return _validate_number(value, field_name)


@dataclass(frozen=True, slots=True)
class GeoPosition:
    """Domain-neutral position evidence."""

    latitude: float
    longitude: float
    altitude: float | None = None
    datum: str | None = None
    uncertainty: float | None = None

    def __post_init__(self) -> None:
        latitude = _validate_number(self.latitude, "latitude")
        longitude = _validate_number(self.longitude, "longitude")
        if not -90.0 <= latitude <= 90.0:
            raise ObservationValidationError(
                "latitude must be between -90.0 and 90.0"
            )
        if not -180.0 <= longitude <= 180.0:
            raise ObservationValidationError(
                "longitude must be between -180.0 and 180.0"
            )
        object.__setattr__(self, "latitude", latitude)
        object.__setattr__(self, "longitude", longitude)
        object.__setattr__(
            self, "altitude", _validate_optional_number(self.altitude, "altitude")
        )
        if self.datum is not None:
            object.__setattr__(self, "datum", _require_non_blank(self.datum, "datum"))
        uncertainty = _validate_optional_number(self.uncertainty, "uncertainty")
        if uncertainty is not None and uncertainty < 0.0:
            raise ObservationValidationError("uncertainty must be non-negative")
        object.__setattr__(self, "uncertainty", uncertainty)


@dataclass
class CrossDomainTag:
    key: str
    value: str

    def __post_init__(self) -> None:
        _require_non_blank(self.key, "key")
        _require_non_blank(self.value, "value")


__all__ = ["CrossDomainTag", "GeoPosition", "ObservationValidationError"]
