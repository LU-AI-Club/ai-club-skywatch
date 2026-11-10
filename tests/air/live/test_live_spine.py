"""Contract tests for the air.live spine.

The spine is complete: A (``read_window``, Spoofing), B (``persist``,
``start_run``, ``finish_run``, Proximity) and C (``run_live``, No-Fly-Zone)
are all implemented, each with its own tests alongside it.

What stays here is the part no single team owns: the shapes the three pieces
agree on. ``read_window``'s signature is imported by B and C, so it is pinned
here rather than in Spoofing's own tests -- a change that breaks them should
fail in a file none of us think of as ours.
"""

from __future__ import annotations

import inspect
from datetime import datetime, timezone
from types import SimpleNamespace

from air.live import (
    PersistResult,
    dedup_key,
    finish_run,
    persist,
    read_window,
    run_live,
    start_run,
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


def test_the_whole_spine_is_implemented() -> None:
    """No stubs left. Asserted, because this file used to track which remained.

    It is cheap to keep honest and expensive to leave stale: while it still
    listed a piece as unimplemented, it read as "that team has not started"
    when they had.
    """
    now = datetime.now(timezone.utc)

    class _Cursor:
        description = [SimpleNamespace(name="entity_id")]

        def execute(self, *args, **kwargs) -> None:
            return None

        def fetchall(self) -> list:
            return []

        def __enter__(self) -> "_Cursor":
            return self

        def __exit__(self, *exc: object) -> None:
            return None

    connection = SimpleNamespace(cursor=lambda: _Cursor())

    # Spine A: an empty window is a quiet minute, not an error.
    assert read_window(connection, start=now, end=now) == []

    # Spine B and C exist and are callable; their behaviour is covered by
    # tests/air/live/test_persistence.py, test_detector_runs.py and the
    # No-Fly-Zone runner tests. Here we only assert they are no longer stubs.
    for piece in (persist, start_run, finish_run, run_live):
        assert callable(piece)
        assert "NotImplementedError" not in (inspect.getsource(piece) or "")
