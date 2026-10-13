"""Tests for epoch-anchored time windowing and the detector runner.

Fixture-free (observations are built in-line), no services. UTC midnight is
divisible by any whole-second step, so ``BASE`` sits exactly on the window grid
and window membership is easy to reason about: with a 10s window, a point at
offset ``t`` seconds falls in window ``[floor(t/10)*10, +10)``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from air.models.observation import AdsbObservation
from air.windowing import detection_dedup_key, iter_windows, run_detectors

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)  # epoch divisible by 10 and 60


def obs(sec: float, *, icao: str = "a1b2c3", alt: float = 1000.0) -> AdsbObservation:
    return AdsbObservation(
        icao24=icao,
        observed_at=BASE + timedelta(seconds=sec),
        latitude=34.0,
        longitude=-80.0,
        altitude_ft=alt,
    )


def test_tumbling_partitions_half_open() -> None:
    windows = list(iter_windows([obs(0), obs(3), obs(9), obs(10), obs(15), obs(25)], 10))
    sizes = [len(w) for w in windows]
    # [0,10)->0,3,9 ; [10,20)->10,15 ; [20,30)->25. t=10 is in the 2nd window.
    assert sizes == [3, 2, 1]


def test_input_is_sorted_before_windowing() -> None:
    windows = list(iter_windows([obs(9), obs(0), obs(3)], 10))
    assert len(windows) == 1
    offsets = [round((o.observed_at - BASE).total_seconds()) for o in windows[0]]
    assert offsets == [0, 3, 9]


def test_empty_gap_windows_are_skipped() -> None:
    # Only two populated 10s windows; the ~9 empty ones in between are not yielded.
    windows = list(iter_windows([obs(0), obs(100)], 10))
    assert len(windows) == 2
    assert [len(w) for w in windows] == [1, 1]


def test_final_partial_window_included() -> None:
    windows = list(iter_windows([obs(0), obs(25)], 10))
    assert len(windows) == 2  # [0,10) and [20,30); [10,20) is empty -> skipped


def test_sliding_windows_overlap_and_keep_straddling_pair_together() -> None:
    # A pair at t=5 and t=15 straddles the tumbling boundary at 10. A 20s window
    # stepping by 10 keeps them in one window.
    windows = list(iter_windows([obs(5, icao="aaaaaa"), obs(15, icao="bbbbbb")], 20, 10))
    assert len(windows) == 2  # starts at 0 -> [0,20); at 10 -> [10,30)
    assert len(windows[0]) == 2  # both points co-occur in the first window
    assert len(windows[1]) == 1  # only t=15 remains in [10,30)


def test_invalid_params_raise() -> None:
    import pytest

    with pytest.raises(ValueError):
        list(iter_windows([obs(0)], 0))
    with pytest.raises(ValueError):
        list(iter_windows([obs(0)], 10, 0))


def test_empty_input_yields_nothing() -> None:
    assert list(iter_windows([], 10)) == []


# --- run_detectors + dedup ----------------------------------------------------
FIXED_START = BASE


class _FakeDetector:
    """Emits one detection per window with an identical dedup key, so
    overlapping windows produce duplicates unless dedup collapses them."""

    detector_id = "fake"

    def detect_observations(self, window: list[AdsbObservation]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                detector_id="fake",
                detector_version="1",
                detection_type="t",
                entities_involved=[SimpleNamespace(entity_id="aircraft:a1")],
                temporal_bounds=SimpleNamespace(start_time=FIXED_START),
            )
        ]


def test_run_detectors_dedup_collapses_overlap() -> None:
    windows = list(iter_windows([obs(5, icao="aaaaaa"), obs(15, icao="bbbbbb")], 20, 10))
    assert len(windows) == 2
    without = list(run_detectors(windows, [_FakeDetector()], dedup=False))
    with_dedup = list(run_detectors(windows, [_FakeDetector()], dedup=True))
    assert len(without) == 2  # one per window
    assert len(with_dedup) == 1  # same key collapsed


def test_detection_dedup_key_ignores_volatile_fields() -> None:
    a = SimpleNamespace(
        detector_id="d", detector_version="1", detection_type="t",
        entities_involved=[SimpleNamespace(entity_id="x")],
        temporal_bounds=SimpleNamespace(start_time=FIXED_START),
        confidence=0.9, detection_id="RANDOM-1",
    )
    b = SimpleNamespace(
        detector_id="d", detector_version="1", detection_type="t",
        entities_involved=[SimpleNamespace(entity_id="x")],
        temporal_bounds=SimpleNamespace(start_time=FIXED_START),
        confidence=0.1, detection_id="RANDOM-2",
    )
    assert detection_dedup_key(a) == detection_dedup_key(b)


# --- end-to-end smoke through the real example detector + contract ------------
def test_end_to_end_with_example_detector() -> None:
    from air.detectors._example_altitude.detector import ExampleAltitudeDetector

    detector = ExampleAltitudeDetector()  # default band [500, 60000] ft
    observations = [obs(0, alt=100.0), obs(1, alt=30000.0)]  # only the 100ft point is out of band
    windows = list(iter_windows(observations, 10))
    detections = list(run_detectors(windows, [detector]))
    assert len(detections) == 1
    assert detections[0].detection_type == "altitude_band_violation"
    assert isinstance(detections[0].to_dict(), dict)  # serializes via the real contract
