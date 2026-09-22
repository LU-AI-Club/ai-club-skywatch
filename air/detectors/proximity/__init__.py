"""skywatch.proximity — dangerous / unusual proximity detector (team-owned)."""

from air.detectors.proximity.config import ProximityConfig, SeverityTier, load_config
from air.detectors.proximity.detector import (
    ProximityDetector,
    confidence_for,
    explanation_facts,
    to_detection,
)
from air.detectors.proximity.features import PairGeometry, pair_geometry
from air.detectors.proximity.rules import flag_pair, severity_for

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
