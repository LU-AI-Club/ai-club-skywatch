from datetime import datetime, timedelta, timezone

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.emit import to_detection
from air.detectors.spoofing.live import extra_columns
from air.detectors.spoofing.records import SpoofingEvent
from contracts import Detection


def test_extra_columns_returns_empty_dict():
    start = datetime(2026, 9, 1, 14, 22, 8, tzinfo=timezone.utc)
    event = SpoofingEvent(
        gate="teleport_v1",
        detection_type="position_jump",
        reason="TELEPORT",
        icao24s=("a1b2c3",),
        observed_from=start,
        observed_to=start + timedelta(seconds=8),
        measured=21_285.0,
        threshold=1000.0,
        unit="kt",
        latitude=37.96,
        longitude=-78.45,
        altitude_ft=34_000.0,
        features=(),
        details={"segment_id": 0, "observation_count": 40},
    )
    detection = to_detection(event, SpoofingConfig())
    before = detection.to_dict()

    assert isinstance(detection, Detection)
    assert extra_columns(detection) == {}
    assert detection.to_dict() == before

