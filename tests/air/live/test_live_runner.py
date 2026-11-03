"""Runner integration tests using the frozen A/B seams and a seeded fixture."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from air.detectors.proximity.detector import ProximityDetector
from air.live import persistence, runner


class _CursorResult:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def fetchone(self) -> tuple[Any]:
        return (self.value,)


class _Connection:
    def execute(self, _query: str, _params: tuple[str]) -> _CursorResult:
        return _CursorResult()

    def commit(self) -> None:
        pass

    def __enter__(self) -> _Connection:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass


def test_cursor_restores_latest_successful_window_end() -> None:
    watermark = datetime(2026, 9, 1, tzinfo=timezone.utc)

    class CursorConnection:
        def execute(self, query: str, params: tuple[str]) -> _CursorResult:
            assert "status = 'SUCCESS'" in query
            assert params == ("skywatch.proximity",)
            return _CursorResult(watermark)

    assert runner._load_cursor(CursorConnection(), "skywatch.proximity") == watermark


class _FlushableProximityDetector(ProximityDetector):
    def __init__(self) -> None:
        super().__init__()
        self.flush_calls = 0

    def flush(self) -> list[Any]:
        self.flush_calls += 1
        return []


def test_once_reads_seeded_fixture_detects_and_persists(
    monkeypatch: Any,
    observations_from: Any,
) -> None:
    observations = observations_from("proximity_head_on.json")
    now = max(observation.observed_at for observation in observations) + timedelta(seconds=1)
    detector = _FlushableProximityDetector()
    persisted: list[Any] = []
    started_runs: list[tuple[datetime, datetime]] = []
    finished_runs: list[str] = []

    def extra_columns(_detection: Any) -> dict[str, bool]:
        return {"fixture": True}

    def read_window(
        _conn: Any,
        *,
        start: datetime,
        end: datetime,
        domain: str,
    ) -> list[Any]:
        assert domain == "air"
        return [
            observation
            for observation in observations
            if start <= observation.observed_at < end
        ]

    def start_run(
        _conn: Any,
        _detector_id: str,
        _detector_version: str,
        *,
        window: tuple[datetime, datetime] | None = None,
    ) -> str:
        assert window is not None
        started_runs.append(window)
        return "fixture-run"

    def persist(
        _conn: Any,
        table: str,
        detections: list[Any],
        *,
        run_id: str | None,
        extra_columns: Any,
    ) -> persistence.PersistResult:
        assert table == "proximity_detections"
        assert run_id == "fixture-run"
        assert extra_columns is not None
        assert extra_columns(detections[0]) == {"fixture": True}
        persisted.extend(detections)
        return persistence.PersistResult(inserted=len(detections))

    def finish_run(
        _conn: Any,
        _run_id: str,
        *,
        status: str,
        counts: dict[str, Any],
    ) -> None:
        assert status == "SUCCESS"
        assert counts["inserted"] == 1
        finished_runs.append(status)

    monkeypatch.setattr(runner, "_connect", lambda _dsn: _Connection())
    monkeypatch.setattr(runner, "_utcnow", lambda: now)
    monkeypatch.setattr(runner.observations_reader, "read_window", read_window)
    monkeypatch.setattr(runner.persistence, "start_run", start_run)
    monkeypatch.setattr(runner.persistence, "persist", persist)
    monkeypatch.setattr(runner.persistence, "finish_run", finish_run)

    runner.run_live(
        detector=detector,
        table="proximity_detections",
        dsn="postgresql://fixture",
        window_s=300,
        step_s=30,
        poll_interval_s=30,
        extra_columns=extra_columns,
        once=True,
    )

    assert len(started_runs) == 1
    assert started_runs[0][0] <= min(obs.observed_at for obs in observations)
    assert started_runs[0][1] == now
    assert len(persisted) == 1
    assert persisted[0].severity.value == "HIGH"
    assert detector.flush_calls == 1
    assert finished_runs == ["SUCCESS"]


def test_once_logs_a_failed_tick_and_marks_run_failed(
    monkeypatch: Any,
    caplog: Any,
) -> None:
    finished: list[str] = []

    def finish_run(
        _conn: Any,
        _run_id: str,
        *,
        status: str,
        counts: dict[str, Any],
    ) -> None:
        finished.append(status)

    def bad_window(*_args: Any, **_kwargs: Any) -> list[Any]:
        raise ValueError("bad window")

    monkeypatch.setattr(runner, "_connect", lambda _dsn: _Connection())
    monkeypatch.setattr(runner, "_utcnow", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr(
        runner.observations_reader,
        "read_window",
        bad_window,
    )
    monkeypatch.setattr(
        runner.persistence,
        "start_run",
        lambda *_args, **_kwargs: "failed-run",
    )
    monkeypatch.setattr(runner.persistence, "finish_run", finish_run)

    with caplog.at_level(logging.ERROR, logger=runner.__name__):
        runner.run_live(
            detector=ProximityDetector(),
            table="proximity_detections",
            dsn="postgresql://fixture",
            window_s=120,
            step_s=30,
            poll_interval_s=30,
            once=True,
        )

    assert finished == ["FAILED"]
    record = next(record for record in caplog.records if record.name == runner.__name__)
    assert record.tick_status == "ERROR"
    assert record.error == "bad window"


def test_continuous_ticks_flush_only_after_shutdown(monkeypatch: Any) -> None:
    class StopAfterTwoTicks:
        def __init__(self) -> None:
            self.wait_calls = 0
            self.stopped = False

        def set(self) -> None:
            self.stopped = True

        def is_set(self) -> bool:
            return self.stopped

        def wait(self, _timeout: float) -> bool:
            self.wait_calls += 1
            if self.wait_calls == 2:
                self.set()
            return self.stopped

    class StatefulDetector:
        detector_id = "fixture.stateful"
        detector_version = "1"

        def __init__(self) -> None:
            self.detect_calls = 0
            self.flush_calls = 0

        def detect_observations(self, _observations: list[Any]) -> list[Any]:
            self.detect_calls += 1
            return []

        def flush(self) -> list[Any]:
            self.flush_calls += 1
            return []

    fake_stop = StopAfterTwoTicks()
    detector = StatefulDetector()
    read_calls = 0
    run_windows: list[tuple[datetime, datetime] | None] = []

    def read_window(*_args: Any, **_kwargs: Any) -> list[Any]:
        nonlocal read_calls
        read_calls += 1
        return []

    def start_run(
        _conn: Any,
        _detector_id: str,
        _detector_version: str,
        *,
        window: tuple[datetime, datetime] | None = None,
    ) -> str:
        run_windows.append(window)
        return "continuous-run"

    monkeypatch.setattr(runner.threading, "Event", lambda: fake_stop)
    monkeypatch.setattr(runner, "_connect", lambda _dsn: _Connection())
    monkeypatch.setattr(runner, "_utcnow", lambda: datetime.now(timezone.utc))
    monkeypatch.setattr(runner.observations_reader, "read_window", read_window)
    monkeypatch.setattr(runner.persistence, "start_run", start_run)
    monkeypatch.setattr(runner.persistence, "finish_run", lambda *_args, **_kwargs: None)

    runner.run_live(
        detector=detector,
        table="fixture_detections",
        dsn="postgresql://fixture",
        window_s=120,
        step_s=30,
        poll_interval_s=30,
    )

    assert read_calls == 2
    assert detector.detect_calls == 2
    assert detector.flush_calls == 1
    assert len(run_windows) == 3
    assert run_windows[-1] is None
