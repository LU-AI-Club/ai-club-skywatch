"""Tests for the output stage: explanation_facts, build_evidence,
build_provenance and to_detection."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.emit import (
    build_evidence,
    build_provenance,
    explanation_facts,
    to_detection,
)
from air.detectors.spoofing.records import SpoofingEvent, SpoofingFeatureRecord
from contracts import Detection, SeverityLevel

CFG = SpoofingConfig()
T0 = datetime(2026, 9, 1, 14, 22, 8, tzinfo=timezone.utc)


def feature() -> SpoofingFeatureRecord:
    return SpoofingFeatureRecord(
        icao24="a1b2c3",
        segment_id=0,
        prev_observed_at=T0,
        curr_observed_at=T0 + timedelta(seconds=8),
        dt_s=8.0,
        dist_m=87_600.0,                       # 47.3 nm
        implied_speed_kt=21_285.0,
        reported_speed_kt=447.0,
        speed_delta_kt=20_838.0,
        curr_latitude=37.96,
        curr_longitude=-78.45,
        altitude_ft=34_000.0,
    )


def event(**overrides) -> SpoofingEvent:
    values = dict(
        gate="teleport_v1",
        detection_type="position_jump",
        reason="TELEPORT",
        icao24s=("a1b2c3",),
        observed_from=T0,
        observed_to=T0 + timedelta(seconds=8),
        measured=21_285.0,
        threshold=1000.0,
        unit="kt",
        latitude=37.96,
        longitude=-78.45,
        altitude_ft=34_000.0,
        features=(feature(),),
        details={"segment_id": 0, "observation_count": 40},
    )
    values.update(overrides)
    return SpoofingEvent(**values)


# --- explanation_facts -------------------------------------------------------
def test_facts_state_the_measurement_and_the_limit():
    facts = " ".join(explanation_facts(event()))
    assert "21,285.0 kt" in facts
    assert "1,000.0 kt" in facts


def test_facts_quote_what_the_aircraft_itself_claimed():
    assert any("447.0 kt" in f for f in explanation_facts(event()))


def test_facts_never_draw_a_conclusion():
    """Deviation is ours to report; intent and threat are not."""
    facts = " ".join(explanation_facts(event())).lower()
    for word in ("spoof", "attack", "threat", "malicious", "deliberate"):
        assert word not in facts


def test_facts_work_for_a_gate_with_no_measurement():
    drift = event(
        gate="identity_drift_v1",
        detection_type="identity_mismatch",
        reason="IDENTITY_DRIFT",
        measured=None,
        threshold=None,
        unit=None,
        features=(),
    )
    assert explanation_facts(drift)


# --- build_evidence ----------------------------------------------------------
def test_evidence_carries_the_arithmetic():
    items = build_evidence(event())
    assert len(items) == 1
    meta = items[0].metadata
    assert meta["dt_s"] == 8.0
    assert meta["implied_speed_kt"] == 21_285.0
    assert meta["feature_schema_version"] == "air-features-v1"


def test_an_event_with_no_feature_records_still_has_evidence():
    """Identity findings rest on whole tracks, not one pair."""
    items = build_evidence(event(features=()))
    assert len(items) == 1
    assert items[0].summary


# --- build_provenance --------------------------------------------------------
def test_provenance_records_the_settings_that_applied():
    provenance = build_provenance(event(), SpoofingConfig(teleport_kt=600.0))
    step = provenance.processing_chain[0]
    assert step.transform_id == "skywatch.spoofing"
    assert step.parameters["teleport_kt"] == 600.0


def test_provenance_names_the_gate_that_fired():
    assert build_provenance(event(), CFG).processing_chain[0].step_name == "teleport_v1"


# --- to_detection ------------------------------------------------------------
def test_a_detection_satisfies_the_platform_contract():
    detection = to_detection(event(), CFG)
    assert isinstance(detection, Detection)
    assert detection.detector_id == "skywatch.spoofing"
    assert detection.detection_type == "position_jump"
    assert detection.severity is SeverityLevel.HIGH
    assert 0.0 <= detection.confidence <= 1.0


def test_the_detection_serialises():
    """The platform consumes to_dict(); a value it cannot serialise breaks it."""
    assert to_detection(event(), CFG).to_dict()["detector_id"] == "skywatch.spoofing"


def test_the_aircraft_is_named_as_an_entity():
    detection = to_detection(event(), CFG)
    assert detection.entities_involved[0].entity_id == "aircraft:a1b2c3"
    assert detection.entities_involved[0].domain == "air"


def test_score_and_explanation_ride_in_metadata():
    meta = to_detection(event(), CFG).metadata
    assert meta["gate"] == "teleport_v1"
    assert meta["anomaly_score"] == 1.0
    assert meta["feature_schema_version"] == "air-features-v1"
    assert meta["explanation_facts"]


def test_every_detection_admits_what_it_cannot_tell_you():
    limits = " ".join(to_detection(event(), CFG).metadata["limitations"]).lower()
    assert "intent" in limits


def test_identity_findings_flag_the_privacy_address_programme():
    """Those aircraft are authorised to broadcast an alternate identity."""
    drift = event(
        gate="identity_drift_v1",
        detection_type="identity_mismatch",
        reason="IDENTITY_DRIFT",
        measured=None,
        threshold=None,
        unit=None,
    )
    limits = " ".join(to_detection(drift, CFG).metadata["limitations"]).lower()
    assert "privacy" in limits


def test_trust_is_never_populated():
    """TCE/CAATS owns Trust; we supply evidence only."""
    assert to_detection(event(), CFG).trust_assessment is None


def test_several_aircraft_for_an_identity_finding():
    detection = to_detection(event(icao24s=("a1b2c3", "d4e5f6")), CFG)
    assert len(detection.entities_involved) == 2
