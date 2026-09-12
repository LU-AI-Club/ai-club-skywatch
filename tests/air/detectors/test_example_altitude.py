"""Tests for the worked reference detector.

Study these: this is exactly the kind of fixture-based, no-database test each
detector lane writes. Every one of these passes out of the box.
"""

from __future__ import annotations

from datetime import datetime, timezone

from air.detectors._example_altitude import (
    ExampleAltitudeConfig,
    ExampleAltitudeDetector,
    altitude_confidence,
    altitude_severity,
    flag_altitude,
)
from air.models.observation import AdsbObservation
from contracts import Detection, SeverityLevel


def _obs(altitude_ft, icao24="a1b2c3"):
    return AdsbObservation(
        icao24=icao24,
        observed_at=datetime(2026, 9, 12, 14, 0, tzinfo=timezone.utc),
        latitude=37.6,
        longitude=-122.4,
        altitude_ft=altitude_ft,
    )


def test_flag_in_band_returns_none():
    cfg = ExampleAltitudeConfig()
    assert flag_altitude(_obs(35000), cfg) is None


def test_flag_above_ceiling():
    cfg = ExampleAltitudeConfig()
    assert flag_altitude(_obs(75000), cfg) == "ABOVE_CEILING"


def test_flag_below_floor():
    cfg = ExampleAltitudeConfig()
    assert flag_altitude(_obs(100), cfg) == "BELOW_FLOOR"


def test_missing_altitude_abstains():
    cfg = ExampleAltitudeConfig()
    assert flag_altitude(_obs(None), cfg) is None


def test_confidence_grows_with_overshoot():
    cfg = ExampleAltitudeConfig()
    near = altitude_confidence(_obs(cfg.ceiling_ft + 100), cfg)
    far = altitude_confidence(_obs(cfg.ceiling_ft + 5000), cfg)
    assert 0.0 <= near <= far <= 1.0


def test_severity_high_when_far_out():
    cfg = ExampleAltitudeConfig()
    assert altitude_severity(_obs(cfg.ceiling_ft + 2000), cfg) is SeverityLevel.HIGH


def test_detector_emits_valid_detection():
    detector = ExampleAltitudeDetector()
    detections = detector.detect_observations([_obs(35000), _obs(75000), _obs(100)])
    # Two out-of-band observations -> two detections; the cruise one is ignored.
    assert len(detections) == 2
    assert all(isinstance(d, Detection) for d in detections)
    payload = detections[0].to_dict()
    assert payload["detector_id"] == "skywatch.example_altitude"
    assert payload["metadata"]["explanation_facts"]


def test_detector_via_context():
    from contracts import DetectionContext

    detector = ExampleAltitudeDetector()
    ctx = DetectionContext(auxiliary_data={"observations": [_obs(75000)]})
    detections = detector.detect(ctx)
    assert len(detections) == 1
