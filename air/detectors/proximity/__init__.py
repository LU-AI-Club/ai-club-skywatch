"""skywatch.proximity — dangerous / unusual proximity detector (team-owned)."""

from air.detectors.proximity.config import ProximityConfig, SeverityTier, load_config
from air.detectors.proximity.detector import (
    PairGeometry,
    ProximityDetector,
    confidence_for,
    explanation_facts,
    flag_pair,
    pair_geometry,
    severity_for,
    to_detection,
)

__all__ = [
    "PairGeometry",
    "ProximityConfig",
    "ProximityDetector",
    "SeverityTier",
    "confidence_for",
    "explanation_facts",
    "flag_pair",
    "load_config",
    "pair_geometry",
    "severity_for",
    "to_detection",
]
