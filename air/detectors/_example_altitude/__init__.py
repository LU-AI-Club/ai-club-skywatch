"""Worked reference detector. Copy this package's SHAPE for real detectors."""

from air.detectors._example_altitude.detector import (
    ExampleAltitudeConfig,
    ExampleAltitudeDetector,
    altitude_confidence,
    altitude_severity,
    flag_altitude,
    to_detection,
)

__all__ = [
    "ExampleAltitudeConfig",
    "ExampleAltitudeDetector",
    "altitude_confidence",
    "altitude_severity",
    "flag_altitude",
    "to_detection",
]
