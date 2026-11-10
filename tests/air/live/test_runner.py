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


_T0 = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
_COUNTS = {"observations": 0, "detections": 0, "inserted": 0, "updated": 0, "skipped": 0}


def _result(lag_s: float = 0.0) -> runner.TickResult:
    return runner.TickResult(start=_T0 - timedelta(seconds=300), end=_T0, lag_s=lag_s,
                             counts=dict(_COUNTS))


def _recording_tick(ticks: list[dict], lags: list[float] | None = None):
    """A fake _tick that records its kwargs and reports the given lags in turn."""
    def fake(**kwargs):
        ticks.append(kwargs)
        lag = lags[len(ticks) - 1] if lags and len(ticks) <= len(lags) else 0.0
        return _result(lag)
    return fake


def test_once_runs_one_tick_and_does_not_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks: list[dict] = []
    sleeps: list[float] = []
    monkeypatch.setattr(runner, "_tick", _recording_tick(ticks))
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)

    _call_run_live(once=True)

    assert len(ticks) == 1
    assert sleeps == []
    assert ticks[0]["flush"] is True  # a single pass is a whole stream


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

    monkeypatch.setattr(runner, "_tick", _recording_tick(ticks))
    monkeypatch.setattr(runner.time, "sleep", fake_sleep)

    with pytest.raises(_StopLoop):
        _call_run_live(once=False)

    assert len(ticks) == 2
    assert sleeps == [30, 30]
    assert ticks[0]["table"] == "test_detections"
    # Never between ticks: flushing would close open findings every tick.
    assert [tick["flush"] for tick in ticks] == [False, False]


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

# --- Catch-up, resilience, shutdown (SPINE_PLAN.md, component C) -------------

def _stop_after(sleeps: list[float], n: int):
    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == n:
            raise _StopLoop
    return fake_sleep


def test_runner_does_not_sleep_while_behind_and_trims_small_lag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Restarted 90 s behind: run windows back to back until current, then
    # sleep only what is left of the interval. Sleeping the full interval
    # after every tick drifted ~24 min behind per day and never caught up.
    ticks: list[dict] = []
    sleeps: list[float] = []
    monkeypatch.setattr(runner, "_tick", _recording_tick(ticks, lags=[90, 60, 2, 0]))
    monkeypatch.setattr(runner.time, "sleep", _stop_after(sleeps, 2))

    with pytest.raises(_StopLoop):
        _call_run_live(once=False)

    assert len(ticks) == 4
    assert sleeps == [28, 30]


def test_a_failed_tick_does_not_kill_the_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def flaky(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise ConnectionError("database restarting")
        return _result()

    sleeps: list[float] = []
    monkeypatch.setattr(runner, "_tick", flaky)
    monkeypatch.setattr(runner.time, "sleep", _stop_after(sleeps, 2))

    with pytest.raises(_StopLoop):
        _call_run_live(once=False)

    assert len(calls) == 2                       # it retried
    assert calls[0]["detector"] is calls[1]["detector"]   # same detector, state kept
    assert sleeps == [30, 30]                    # back-off, then the normal interval


def test_failures_back_off_exponentially_up_to_a_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    def always_down(**_kwargs):
        raise ConnectionError("database down")

    sleeps: list[float] = []
    monkeypatch.setattr(runner, "_tick", always_down)
    monkeypatch.setattr(runner.time, "sleep", _stop_after(sleeps, 6))

    with pytest.raises(_StopLoop):
        _call_run_live(once=False)

    assert sleeps == [30, 60, 120, 240, 300, 300]


def test_once_still_raises_so_ci_sees_the_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(**_kwargs):
        raise ConnectionError("no database")

    monkeypatch.setattr(runner, "_tick", broken)
    with pytest.raises(ConnectionError):
        _call_run_live(once=True)


def test_sigterm_finishes_the_tick_then_flushes_and_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import signal

    ticks: list[dict] = []

    def tick(**kwargs):
        ticks.append(kwargs)
        if len(ticks) == 2:
            os.kill(os.getpid(), signal.SIGTERM)   # docker compose down, mid-tick
        return _result()

    monkeypatch.setattr(runner, "_tick", tick)
    monkeypatch.setattr(runner.time, "sleep", lambda _s: None)
    detector = SimpleNamespace(detector_id="test.detector", flush=lambda: [])

    run_live(detector=detector, table="t", dsn="postgresql://test", window_s=300,
             step_s=30, poll_interval_s=30)          # returns instead of looping forever

    assert [t["flush"] for t in ticks] == [False, False, True]  # last: close what is open
    assert signal.getsignal(signal.SIGTERM) is not runner._StopSignal._handle


def test_sigterm_during_the_sleep_stops_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    import os
    import signal
    import threading
    import time as real_time

    monkeypatch.setattr(runner, "_tick", _recording_tick([]))
    threading.Timer(0.2, os.kill, (os.getpid(), signal.SIGTERM)).start()
    started = real_time.monotonic()
    _call_run_live(once=False)                        # would otherwise sleep 30 s
    assert real_time.monotonic() - started < 5


def test_detections_from_a_failed_tick_are_saved_by_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The detector has moved past them, so re-reading the window would not
    # produce them again; they must be carried to the next tick.
    import sys
    import types

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def rollback(self):
            pass

    monkeypatch.setitem(sys.modules, "psycopg", types.SimpleNamespace(connect=lambda _dsn: Conn()))
    monkeypatch.setattr(runner, "_load_cursor", lambda *_a: None)
    monkeypatch.setattr(runner, "_save_cursor", lambda *_a: None)
    monkeypatch.setattr(runner, "start_run", lambda *_a, **_k: "run")
    monkeypatch.setattr(runner, "finish_run", lambda *_a, **_k: None)
    monkeypatch.setattr(runner, "read_window", lambda *_a, **_k: [])
    stored: list[list] = []
    outcomes = iter([ConnectionError("write failed"), None])

    def persist(_conn, _table, detections, **_k):
        failure = next(outcomes)
        if failure:
            raise failure
        stored.append(list(detections))
        return SimpleNamespace(inserted=len(detections), updated=0, skipped=0)

    monkeypatch.setattr(runner, "persist", persist)
    found = iter([["incursion"], []])
    detector = SimpleNamespace(detector_id="d", detect_observations=lambda _obs: next(found))
    pending: list = []
    args = {"detector": detector, "table": "t", "dsn": "x", "window_s": 300, "step_s": 30,
            "extra_columns": None, "domain": "air", "flush": False, "pending": pending}

    with pytest.raises(ConnectionError):
        runner._tick(**args)
    assert pending == ["incursion"]

    runner._tick(**args)
    assert stored == [["incursion"]] and pending == []
