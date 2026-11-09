"""Contract tests for the air.live spine stubs.

Keeps CI green from day 1 and locks the two pieces that are implemented now
(``PersistResult`` and ``dedup_key``). The owning teams replace the
NotImplementedError stubs with real behavior and their own fixture tests.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

from air.live import (
    PersistResult,
    dedup_key,
    read_window,
)


def test_persist_result_defaults() -> None:
    result = PersistResult()
    assert (result.inserted, result.updated, result.skipped) == (0, 0, 0)


def test_dedup_key_is_a_stable_string() -> None:
    # A duck-typed stand-in: dedup_key only needs the fields
    # air.windowing.detection_dedup_key reads, so the test needs no DB or a
    # fully constructed Detection.
    detection = SimpleNamespace(
        detector_id="skywatch.spoofing",
        detector_version="0.1.0",
        detection_type="position_jump",
        entities_involved=[SimpleNamespace(entity_id="aircraft:a1b2c3")],
        temporal_bounds=SimpleNamespace(
            start_time=datetime(2026, 1, 1, tzinfo=timezone.utc)
        ),
    )
    key = dedup_key(detection)
    assert isinstance(key, str)
    assert key == dedup_key(detection)  # deterministic
    assert "a1b2c3" in key


def test_read_window_keeps_its_frozen_signature() -> None:
    """Spine A is implemented now; this is the contract B and C import.

    Proximity and No-Fly-Zone call ``read_window`` and nothing else in the
    reader, so a change here breaks them. Keyword-only after ``conn``, and
    ``domain`` defaults to air.
    """
    signature = inspect.signature(read_window)
    parameters = signature.parameters
    assert list(parameters) == ["conn", "start", "end", "domain"]
    assert parameters["start"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["end"].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters["domain"].default == "air"
