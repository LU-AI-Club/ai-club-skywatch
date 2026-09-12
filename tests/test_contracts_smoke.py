"""Smoke test for the vendored SENTINEL contracts.

Proves the output contract is importable and round-trips to a dict. This is
what guarantees a SkyWatch Detection can flow into the real TCE/CAATS pipeline.
"""

from __future__ import annotations

from datetime import datetime, timezone

from contracts import (
    Detection,
    EntityRef,
    GeoContext,
    GeoPosition,
    ProvenanceRecord,
    SeverityLevel,
    TimeBounds,
)


def test_detection_round_trips_to_dict():
    detection = Detection(
        detector_id="skywatch.example",
        detector_version="0.1.0",
        detection_type="smoke_test",
        severity=SeverityLevel.INFO,
        confidence=0.5,
        temporal_bounds=TimeBounds(start_time=datetime(2026, 9, 12, tzinfo=timezone.utc)),
        provenance=ProvenanceRecord(source_system="skywatch"),
        entities_involved=[
            EntityRef(entity_id="aircraft:a1b2c3", entity_type="aircraft", domain="air")
        ],
        geospatial_context=GeoContext(
            centroid=GeoPosition(latitude=37.6, longitude=-122.4, altitude=35000)
        ),
    )

    payload = detection.to_dict()

    assert payload["detector_id"] == "skywatch.example"
    assert payload["severity"] == "INFO"
    assert payload["entities_involved"][0]["entity_id"] == "aircraft:a1b2c3"
    # Provenance travels with every detection (SENTINEL "lineage by default").
    assert payload["provenance"]["source_system"] == "skywatch"


def test_severity_accepts_string_alias():
    detection = Detection(
        detector_id="skywatch.example",
        detector_version="0.1.0",
        detection_type="smoke_test",
        severity="high",  # normalized to the enum
        confidence=0.9,
        temporal_bounds=TimeBounds(start_time=datetime(2026, 9, 12, tzinfo=timezone.utc)),
        provenance=ProvenanceRecord(source_system="skywatch"),
    )
    assert detection.severity is SeverityLevel.HIGH
