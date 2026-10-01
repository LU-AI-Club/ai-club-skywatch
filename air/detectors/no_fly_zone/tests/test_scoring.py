"""Stream G tests - logic/scoring.py."""
from __future__ import annotations

from typing import TYPE_CHECKING, cast

from ..config import Config
from ..logic.scoring import build_detection
from ..types import (
    Activation,
    ActivationResult,
    ActivationState,
    AirspaceZone,
    AltitudeSource,
    ContainmentResult,
    Datum,
    Severity,
    VerticalResult,
    ZoneType,
)
from .conftest import make_state

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry


def _zone() -> AirspaceZone:
    return AirspaceZone(
        zone_id="P-56",
        name="Test prohibited area",
        zone_type=ZoneType.PROHIBITED,
        geometry=cast("BaseGeometry", None),
        floor_ft=0.0,
        floor_datum=Datum.SFC,
        ceiling_ft=10000.0,
        ceiling_datum=Datum.MSL,
        activation=Activation.ALWAYS,
    )


def test_prohibited_incursion_scores_high(cfg: Config) -> None:
    """PROHIBITED incursions score strongly and pin the airspace cycle."""
    detection = build_detection(
        state=make_state(),
        zone=_zone(),
        containment=ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        vertical=VerticalResult(
            within=True,
            altitude_ft=5200.0,
            altitude_source=AltitudeSource.GEOMETRIC,
        ),
        activation=ActivationResult(
            state=ActivationState.ACTIVE,
            zone_id="P-56",
            basis="always active",
        ),
        signals=(),
        cfg=cfg,
    )

    assert detection.anomaly_score >= 0.9
    assert detection.severity is Severity.HIGH
    assert detection.baseline_or_model_version.endswith("sua-2026-08-07")
    assert detection.extras["source_row_id"] == "test-1"
    assert detection.explanation_facts


def test_unknown_activation_caps_severity(cfg: Config) -> None:
    """Unknown activation caps a potential incursion at the configured severity."""
    detection = build_detection(
        state=make_state(),
        zone=_zone(),
        containment=ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        vertical=VerticalResult(
            within=True,
            altitude_ft=5200.0,
            altitude_source=AltitudeSource.GEOMETRIC,
        ),
        activation=ActivationResult(
            state=ActivationState.UNKNOWN,
            zone_id="P-56",
            basis="NOTAM activation could not be resolved",
        ),
        signals=(),
        cfg=cfg,
    )

    assert detection.severity is Severity.LOW
    assert detection.raw_model_confidence == 0.0
    assert "Zone activation could not be determined." in detection.limitations
