"""Tests for the two contracts passed between the detector's stages.

These records are agreements, not logic. What is worth testing is that they
reject the shapes that would quietly corrupt everything downstream: a
non-positive time gap, an empty aircraft list, a backwards time window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.records import SpoofingEvent, SpoofingFeatureRecord

T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(seconds=8)


def _record(**overrides) -> SpoofingFeatureRecord:
    values = dict(
        icao24="a1b2c3",
        segment_id=0,
        prev_observed_at=T0,
        curr_observed_at=T1,
        dt_s=8.0,
        dist_m=87_600.0,
        implied_speed_kt=21_285.0,
        reported_speed_kt=447.0,
        speed_delta_kt=20_838.0,
    )
    values.update(overrides)
    return SpoofingFeatureRecord(**values)


def _event(**overrides) -> SpoofingEvent:
    values = dict(
        gate="teleport_v1",
        detection_type="position_jump",
        reason="TELEPORT",
        icao24s=("a1b2c3",),
        observed_from=T0,
        observed_to=T1,
        measured=21_285.0,
        threshold=1000.0,
        unit="kt",
    )
    values.update(overrides)
    return SpoofingEvent(**values)


# --- SpoofingFeatureRecord ---------------------------------------------------
def test_a_valid_record_keeps_its_values():
    record = _record()
    assert record.icao24 == "a1b2c3"
    assert record.dt_s == 8.0
    assert record.implied_speed_kt == 21_285.0


def test_optional_features_default_to_none():
    """Not reported is None, never 0 - rules must abstain on it."""
    record = _record()
    assert record.turn_rate_dps is None
    assert record.vrate_delta_fpm is None
    assert record.agl_ft is None


@pytest.mark.parametrize("dt_s", [0.0, -1.0])
def test_non_positive_time_gap_is_rejected(dt_s):
    """A zero or negative gap would imply infinite speed downstream."""
    with pytest.raises(ValueError, match="dt_s"):
        _record(dt_s=dt_s)


def test_negative_distance_is_rejected():
    with pytest.raises(ValueError, match="dist_m"):
        _record(dist_m=-1.0)


def test_blank_aircraft_id_is_rejected():
    with pytest.raises(ValueError, match="icao24"):
        _record(icao24="   ")


def test_schema_version_is_stamped():
    """Every Detection carries this, so an alert stays interpretable."""
    assert _record().feature_schema_version == "air-features-v1"


def test_the_record_is_frozen():
    """Rules read features; nothing downstream may rewrite them."""
    with pytest.raises(Exception):
        _record().dt_s = 99.0


# --- SpoofingEvent -----------------------------------------------------------
def test_a_valid_event_keeps_its_values():
    event = _event()
    assert event.gate == "teleport_v1"
    assert event.reason == "TELEPORT"
    assert event.icao24s == ("a1b2c3",)
    assert event.unit == "kt"


def test_an_event_carries_no_score_or_severity():
    """Those are the scoring lane's job, computed from measured vs threshold."""
    assert not hasattr(_event(), "anomaly_score")
    assert not hasattr(_event(), "severity")


@pytest.mark.parametrize("field_name", ["gate", "detection_type", "reason"])
def test_blank_identifying_strings_are_rejected(field_name):
    with pytest.raises(ValueError, match=field_name):
        _event(**{field_name: "  "})


def test_an_event_must_name_an_aircraft():
    with pytest.raises(ValueError, match="icao24s"):
        _event(icao24s=())


def test_a_backwards_time_window_is_rejected():
    with pytest.raises(ValueError, match="observed_to"):
        _event(observed_from=T1, observed_to=T0)


def test_identity_drift_may_carry_no_measurement():
    """It is the one gate that is a yes/no, with nothing to measure."""
    event = _event(
        gate="identity_drift_v1",
        detection_type="identity_mismatch",
        reason="IDENTITY_DRIFT",
        measured=None,
        threshold=None,
        unit=None,
    )
    assert event.measured is None
    assert event.threshold is None


def test_several_aircraft_for_an_identity_finding():
    """Coexistence names more than one id by design."""
    event = _event(icao24s=("a1b2c3", "d4e5f6"))
    assert len(event.icao24s) == 2


# --- to_parameters -----------------------------------------------------------
def test_to_parameters_flattens_the_event():
    params = _event().to_parameters()
    assert params["gate"] == "teleport_v1"
    assert params["measured"] == 21_285.0
    assert params["threshold"] == 1000.0
    assert params["unit"] == "kt"


def test_to_parameters_leaves_out_the_evidence():
    """features holds whole records; Detection metadata wants flat values."""
    params = _event(features=(_record(),)).to_parameters()
    assert "features" not in params


def test_to_parameters_covers_every_other_field():
    event = _event()
    expected = {
        "gate", "detection_type", "reason", "icao24s", "observed_from",
        "observed_to", "measured", "threshold", "unit", "latitude",
        "longitude", "altitude_ft", "details",
    }
    assert set(event.to_parameters()) == expected
