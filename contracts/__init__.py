"""SENTINEL contracts — vendored, read-only.

This package is a faithful copy of the SENTINEL platform's detection output
contract. SkyWatch detectors IMPORT from here and must never redefine these
types: emitting the real ``Detection`` is what makes Week-11 TCE/CAATS
integration a wiring exercise instead of a rewrite.

Do not hand-edit files in this package. See contracts/README.md for how to
re-sync from the platform.
"""

from contracts.base import (
    BaseDetector,
    DataRequirements,
    DetectionContext,
    DetectorImplementationType,
    DetectorMetadata,
    ObservationRecord,
)
from contracts.detection import (
    Detection,
    EntityRef,
    Evidence,
    FeatureAttribution,
    GeoContext,
    GraphAttentionAttribution,
    Identifier,
    PredictionIntervalAttribution,
    SeverityLevel,
    TimeBounds,
)
from contracts.entity import CrossDomainTag, GeoPosition
from contracts.provenance import (
    ProcessingStep,
    ProvenanceChain,
    ProvenanceRecord,
    QualityAssessment,
)

__all__ = [
    "BaseDetector",
    "CrossDomainTag",
    "DataRequirements",
    "Detection",
    "DetectionContext",
    "DetectorImplementationType",
    "DetectorMetadata",
    "EntityRef",
    "Evidence",
    "FeatureAttribution",
    "GeoContext",
    "GeoPosition",
    "GraphAttentionAttribution",
    "Identifier",
    "ObservationRecord",
    "PredictionIntervalAttribution",
    "ProcessingStep",
    "ProvenanceChain",
    "ProvenanceRecord",
    "QualityAssessment",
    "SeverityLevel",
    "TimeBounds",
]
