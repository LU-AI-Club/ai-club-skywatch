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

def build_detector(config: ProximityConfig | None = None) -> ProximityDetector:
    """Factory the shared replay runner looks for (scripts/replay_csv.py).

    Zero-arg by default: loads configs/detectors/proximity.yaml. Pass a config
    to override the rule set for threshold sweeps or evaluation runs.
    """
    return ProximityDetector(config)


__all__ = [
    "PairGeometry",
    "ProximityConfig",
    "ProximityDetector",
    "SeverityTier",
    "build_detector",
    "confidence_for",
    "explanation_facts",
    "flag_pair",
    "load_config",
    "pair_geometry",
    "severity_for",
    "to_detection",
]
