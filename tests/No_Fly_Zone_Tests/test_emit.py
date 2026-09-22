"""Tests for emit.py - the bridge to the vendored SENTINEL contract.

These are IMPLEMENTED and run today. They are the proof that a Detection this
detector produces is actually accepted by contracts/detection.py, so nobody
discovers in Week 11 that the shape was wrong all along.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from contracts import Detection as PlatformDetection
from contracts import SeverityLevel

from ...air.detectors.no_fly_zone.emit import to_platform_detection
from ...air.detectors.no_fly_zone.types import Detection, Severity

OBSERVED_AT = datetime(2026, 9, 22, 20, 15, tzinfo=UTC)


def _internal(**overrides: object) -> Detection:
    """A representative internal Detection: P-901 incursion, fully populated."""
    extras: dict[str, object] = {
        "observed_at": OBSERVED_AT,
        "source_row_id": "fixture-1",
        "lat": 37.425,
        "lon": -79.215,
        "altitude_ft": 5200.0,
        "zone_id": "P-901",
        "penetration_nm": 1.5,
    }
    base: dict[str, object] = {
        "detector_id": "skywatch.no_fly_zone",
        "detector_version": "0.1.0",
        "entity_ids": ("aircraft:a1b2c3",),
        "detection_type": "restricted_airspace_incursion",
        "severity": Severity.HIGH,
        "anomaly_score": 0.91,
        "raw_model_confidence": 0.78,
        "evidence_refs": ("obs:fixture-1",),
        "feature_schema_version": "air-features-v1",
        "baseline_or_model_version": "nfz-rules-0.1.0+sua-2026-08-07",
        "explanation_facts": ("Aircraft entered P-901 at 5200 ft.",),
        "limitations": ("Activation state assumed from published schedule.",),
        "extras": extras,
    }
    base.update(overrides)
    return Detection(**base)  # type: ignore[arg-type]


def test_produces_a_valid_platform_detection() -> None:
    """The contract's own __post_init__ validation must accept our output."""
    out = to_platform_detection(_internal())
    assert isinstance(out, PlatformDetection)
    assert out.detector_id == "skywatch.no_fly_zone"
    assert out.detection_type == "restricted_airspace_incursion"
    assert out.severity is SeverityLevel.HIGH


def test_confidence_carries_model_confidence_not_anomaly_score() -> None:
    """The platform has one probability field; ours has two. confidence must be
    raw_model_confidence, and anomaly_score must survive in metadata."""
    out = to_platform_detection(_internal())
    assert out.confidence == 0.78
    assert out.metadata["anomaly_score"] == 0.91


def test_required_platform_fields_are_populated_from_extras() -> None:
    """temporal_bounds and provenance are required by the contract and absent
    from types.Detection, so they must come out of extras."""
    out = to_platform_detection(_internal())
    assert out.temporal_bounds.start_time == OBSERVED_AT
    assert out.provenance.source_system == "skywatch"
    assert out.provenance.raw_source_ref == "fixture-1"
    step = out.provenance.processing_chain[0]
    assert step.transform_version == "nfz-rules-0.1.0+sua-2026-08-07"


def test_geospatial_context_carries_zone_and_depth() -> None:
    """zone_id becomes a risk zone; penetration converts nm -> metres and must
    be non-negative or the contract rejects it."""
    out = to_platform_detection(_internal())
    assert out.geospatial_context.risk_zone_ids == ["P-901"]
    assert out.geospatial_context.centroid is not None
    assert out.geospatial_context.centroid.latitude == 37.425
    assert out.geospatial_context.distance_meters == pytest.approx(2778.0)


def test_explanation_and_limitations_survive_the_crossing() -> None:
    """The platform has no field for either, so they must land in metadata -
    losing them would make a detection unreviewable."""
    out = to_platform_detection(_internal())
    assert out.metadata["explanation_facts"] == ["Aircraft entered P-901 at 5200 ft."]
    assert out.metadata["limitations"] == [
        "Activation state assumed from published schedule."
    ]
    assert out.evidence[0].summary == "Aircraft entered P-901 at 5200 ft."


def test_to_dict_is_json_serializable() -> None:
    """to_dict() is what gets written to detections.jsonl, so it must contain no
    datetimes, enums or UUIDs that json.dumps would choke on."""
    import json

    out = to_platform_detection(_internal())
    encoded = json.dumps(out.to_dict())
    assert '"HIGH"' in encoded
    assert "2026-09-22T20:15:00+00:00" in encoded


@pytest.mark.parametrize("missing", ["observed_at", "source_row_id", "lat", "lon"])
def test_missing_required_extra_names_the_key(missing: str) -> None:
    """Fail loudly and say which key. A fabricated timestamp is worse than no
    detection, because it looks authoritative."""
    extras = dict(_internal().extras)
    del extras[missing]
    with pytest.raises(ValueError, match=missing):
        to_platform_detection(_internal(extras=extras))


def test_every_internal_severity_has_a_platform_equivalent() -> None:
    """Severity maps by name. If someone adds a value to types.Severity that the
    platform lacks, this fails here rather than at emit time in production."""
    for severity in Severity:
        out = to_platform_detection(_internal(severity=severity))
        assert out.severity.value == severity.value
