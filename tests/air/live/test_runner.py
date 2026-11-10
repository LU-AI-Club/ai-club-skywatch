"""Tests for the live runner (Spine C)."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from air.live import runner
from air.live.runner import run_live


def _call_run_live(*, once: bool) -> None:
    """Call run_live with simple test values."""
    run_live(
        detector=SimpleNamespace(detector_id="test.detector"),
        table="test_detections",
        dsn="postgresql://test",
        window_s=300,
        step_s=30,
        poll_interval_s=30,
        once=once,
    )


def test_run_live_signature_is_frozen() -> None:
    parameters = inspect.signature(run_live).parameters

    assert list(parameters) == [
        "detector",
        "table",
        "dsn",
        "window_s",
        "step_s",
        "poll_interval_s",
        "extra_columns",
        "domain",
        "once",
    ]
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in parameters.values())
    assert parameters["extra_columns"].default is None
    assert parameters["domain"].default == "air"
    assert parameters["once"].default is False


def test_once_runs_one_tick_and_does_not_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks: list[dict] = []
    sleeps: list[float] = []
    monkeypatch.setattr(runner, "_tick", lambda **kwargs: ticks.append(kwargs))
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)

    _call_run_live(once=True)

    assert len(ticks) == 1
    assert sleeps == []


class _StopLoop(Exception):
    """Raised by the fake sleep to break out of the endless loop."""


def test_continuous_mode_keeps_ticking_and_sleeps_between_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks: list[dict] = []
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise _StopLoop

    monkeypatch.setattr(runner, "_tick", lambda **kwargs: ticks.append(kwargs))
    monkeypatch.setattr(runner.time, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        _call_run_live(once=False)

    assert len(ticks) == 2
    assert sleeps == [30, 30]
    assert ticks[0]["table"] == "test_detections"


@pytest.mark.parametrize(
    ("parameter", "value"),
    [
        ("window_s", 0),
        ("step_s", 0),
        ("step_s", 301),
        ("poll_interval_s", 0),
    ],
)
def test_run_live_rejects_invalid_timing(
    monkeypatch: pytest.MonkeyPatch,
    parameter: str,
    value: float,
) -> None:
    kwargs = {
        "detector": SimpleNamespace(detector_id="test.detector"),
        "table": "test_detections",
        "dsn": "postgresql://test",
        "window_s": 300,
        "step_s": 30,
        "poll_interval_s": 30,
        "once": True,
    }
    kwargs[parameter] = value
    monkeypatch.setattr(
        runner,
        "_tick",
        lambda **_: pytest.fail("invalid timing must fail before starting a tick"),
    )

    with pytest.raises(ValueError):
        run_live(**kwargs)


class _FakeCursor:
    def __init__(self, row: tuple[datetime] | None = None) -> None:
        self.row = row
        self.executed: tuple[str, tuple[object, ...]] | None = None

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.executed = query, params

    def fetchone(self) -> tuple[datetime] | None:
        return self.row


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self.fake_cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self.fake_cursor


def test_cursor_load_normalizes_utc_and_returns_none_when_unset() -> None:
    local_cursor = datetime(2026, 11, 3, 12, tzinfo=timezone(timedelta(hours=-5)))
    cursor = _FakeCursor((local_cursor,))
    conn = _FakeConnection(cursor)

    assert runner._load_cursor(conn, "test.detector") == datetime(
        2026, 11, 3, 17, tzinfo=UTC
    )
    assert cursor.executed == (runner._CURSOR_SELECT, ("test.detector",))
    assert runner._load_cursor(_FakeConnection(_FakeCursor()), "test.detector") is None


def test_cursor_save_uses_monotonic_upsert() -> None:
    cursor = _FakeCursor()
    conn = _FakeConnection(cursor)
    cursor_at = datetime(2026, 11, 3, 17, tzinfo=UTC)

    runner._save_cursor(conn, "test.detector", cursor_at)

    assert cursor.executed == (runner._CURSOR_UPSERT, ("test.detector", cursor_at))
    assert "GREATEST" in runner._CURSOR_UPSERT


def test_window_bounds_use_restored_cursor_and_bounded_lookback() -> None:
    now = datetime(2026, 11, 3, 17, tzinfo=UTC)
    cursor_at = now - timedelta(seconds=30)

    start, end = runner._window_bounds(
        cursor_at=cursor_at,
        now=now,
        window_s=300,
        step_s=30,
    )

    assert start == now - timedelta(seconds=300)
    assert end == now


def test_initial_window_starts_one_lookback_before_now() -> None:
    now = datetime(2026, 11, 3, 17, tzinfo=UTC)

    assert runner._window_bounds(
        cursor_at=None,
        now=now,
        window_s=300,
        step_s=30,
    ) == (
        now - timedelta(seconds=300),
        now,
    )


def test_window_end_catches_up_by_one_step_without_exceeding_now() -> None:
    now = datetime(2026, 11, 3, 17, tzinfo=UTC)
    cursor_at = now - timedelta(seconds=600)

    start, end = runner._window_bounds(
        cursor_at=cursor_at,
        now=now,
        window_s=300,
        step_s=30,
    )

    assert end == now - timedelta(seconds=570)
    assert start == end - timedelta(seconds=300)