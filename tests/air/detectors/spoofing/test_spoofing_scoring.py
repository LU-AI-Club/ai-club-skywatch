"""Tests for scoring: anomaly_score, confidence_for, severity_for, should_abstain."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.records import SpoofingEvent, SpoofingFeatureRecord
from air.detectors.spoofing.scoring import (
    UNMEASURED_SCORE,
    anomaly_score,
    confidence_for,
    severity_for,
    should_abstain,
)
from contracts import SeverityLevel

CFG = SpoofingConfig()
T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def feature(dt_s: float = 8.0) -> SpoofingFeatureRecord:
    return SpoofingFeatureRecord(
        icao24="a1b2c3",
        segment_id=0,
        prev_observed_at=T0,
        curr_observed_at=T0 + timedelta(seconds=dt_s),
        dt_s=dt_s,
        dist_m=1000.0,
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
        features=(feature(),),
        details={"segment_id": 0, "observation_count": 40},
    )
    values.update(overrides)
    return SpoofingEvent(**values)


# --- anomaly_score -----------------------------------------------------------
def test_exactly_at_the_limit_scores_a_half():
    assert anomaly_score(1000.0, 1000.0) == 0.5


def test_a_modest_overshoot_scores_just_above_a_half():
    """10% over the limit is barely anomalous and should read that way."""
    assert anomaly_score(1100.0, 1000.0) == pytest.approx(0.55)


def test_a_one_knot_overshoot_rounds_back_to_the_line():
    """Scores carry 3 decimals, so a trivial overshoot is not distinguished."""
    assert anomaly_score(1001.0, 1000.0) == 0.5


def test_wildly_over_saturates_at_one():
    assert anomaly_score(21_285.0, 1000.0) == 1.0


def test_under_the_limit_never_exceeds_a_half():
    assert anomaly_score(500.0, 1000.0) == 0.5


def test_the_sign_does_not_matter():
    """Disagreements run both ways; magnitude is what counts."""
    assert anomaly_score(-3000.0, 2000.0) == anomaly_score(3000.0, 2000.0)


def test_a_gate_with_nothing_to_measure_still_scores():
    """identity_drift_v1 is a yes or no. It fired, so it is not zero."""
    assert anomaly_score(None, None) == UNMEASURED_SCORE
    assert anomaly_score(5.0, None) == UNMEASURED_SCORE


# --- confidence_for ----------------------------------------------------------
def test_good_evidence_scores_full_confidence():
    assert confidence_for(event(), CFG) == 1.0


def test_a_very_short_gap_lowers_confidence():
    """Below a second, timestamp error dominates the arithmetic."""
    assert confidence_for(event(features=(feature(dt_s=0.6),)), CFG) < 1.0


def test_a_thin_segment_lowers_confidence():
    """Two reports is not enough to establish anything."""
    thin = event(details={"segment_id": 0, "observation_count": 2})
    assert confidence_for(thin, CFG) < 1.0


def test_a_gate_with_no_measurement_lowers_confidence():
    drift = event(
        gate="identity_drift_v1", measured=None, threshold=None, unit=None
    )
    assert confidence_for(drift, CFG) < 1.0


def test_confidence_stays_within_bounds():
    worst = event(
        measured=None,
        threshold=None,
        unit=None,
        features=(feature(dt_s=0.1),),
        details={"observation_count": 1},
    )
    assert 0.0 <= confidence_for(worst, CFG) <= 1.0


# --- severity_for ------------------------------------------------------------
@pytest.mark.parametrize(
    "gate, expected",
    [
        ("teleport_v1", SeverityLevel.HIGH),
        ("turn_rate_v1", SeverityLevel.HIGH),
        ("coexistence_v1", SeverityLevel.HIGH),
        ("speed_delta_v1", SeverityLevel.MEDIUM),
        ("vrate_delta_v1", SeverityLevel.MEDIUM),
        ("nic_floor_v1", SeverityLevel.LOW),
        ("identity_drift_v1", SeverityLevel.LOW),
    ],
)
def test_severity_follows_the_tier(gate, expected):
    assert severity_for(gate) is expected


def test_an_unknown_gate_is_low_not_an_error():
    """A new rule must not crash the pipeline on its first run."""
    assert severity_for("something_new_v1") is SeverityLevel.LOW


# --- should_abstain ----------------------------------------------------------
def test_strong_evidence_alerts():
    assert should_abstain(score=1.0, confidence=0.94, cfg=CFG) is False


def test_thin_evidence_stays_quiet_however_extreme():
    """20,000 kt off two sparse reports is exactly this case."""
    assert should_abstain(score=1.0, confidence=0.2, cfg=CFG) is True


def test_the_floor_is_configurable():
    strict = SpoofingConfig(min_confidence=0.95)
    assert should_abstain(score=1.0, confidence=0.9, cfg=strict) is True
