"""detector_runs heartbeat: start_run / finish_run leave one row per run.

No database: ``FakeConn`` is a tiny in-memory stand-in for a psycopg connection
that applies the two statements ``start_run`` and ``finish_run`` send.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from air.detectors.proximity import ProximityDetector
from air.live import finish_run, start_run
from tests.conftest import load_observations

MIGRATION = Path(__file__).resolve().parents[3] / "db" / "schema" / "006_detector_runs.sql"
T0 = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
T1 = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)


class FakeCursor:
    def __init__(self, db: FakeConn) -> None:
        self.db = db
        self.rowcount = -1

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.db.statements.append(sql)
        if sql.startswith("INSERT INTO detector_runs"):
            run_id, detector_id, version, window_start, window_end = params
            self.db.rows[run_id] = {
                "detector_id": detector_id,
                "detector_version": version,
                "window_start": window_start,
                "window_end": window_end,
                "status": "RUNNING",
                "counts": {},
                "completed": False,
            }
            self.rowcount = 1
        elif sql.startswith("UPDATE detector_runs"):
            status, counts_json, run_id = params
            row = self.db.rows.get(run_id)
            self.rowcount = 0 if row is None else 1
            if row is not None:
                row.update(status=status, counts=json.loads(counts_json), completed=True)
        else:
            raise AssertionError(f"unexpected SQL: {sql}")


class FakeConn:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, Any]] = {}
        self.statements: list[str] = []
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_start_run_leaves_one_running_row() -> None:
    conn = FakeConn()
    run_id = start_run(conn, "skywatch.proximity", "0.1.0", window=(T0, T1))

    assert str(uuid.UUID(run_id)) == run_id  # a real UUID, as detection_run_id needs
    assert list(conn.rows) == [run_id]
    row = conn.rows[run_id]
    assert (row["detector_id"], row["detector_version"]) == ("skywatch.proximity", "0.1.0")
    assert (row["window_start"], row["window_end"]) == (T0, T1)
    assert row["status"] == "RUNNING" and not row["completed"]
    assert conn.commits == 1  # heartbeat is visible before the run finishes


def test_start_run_window_is_optional() -> None:
    conn = FakeConn()
    row = conn.rows
    run_id = start_run(conn, "skywatch.proximity", "0.1.0")
    assert (row[run_id]["window_start"], row[run_id]["window_end"]) == (None, None)


def test_each_run_gets_its_own_row() -> None:
    conn = FakeConn()
    first = start_run(conn, "skywatch.proximity", "0.1.0")
    second = start_run(conn, "skywatch.proximity", "0.1.0")
    assert first != second and len(conn.rows) == 2


@pytest.mark.parametrize("status", ["SUCCESS", "FAILED"])
def test_finish_run_records_status_and_counts(status: str) -> None:
    conn = FakeConn()
    run_id = start_run(conn, "skywatch.proximity", "0.1.0")
    finish_run(conn, run_id, status=status, counts={"detections": 3})

    assert len(conn.rows) == 1  # updated in place, not a second row
    assert conn.rows[run_id]["status"] == status
    assert conn.rows[run_id]["counts"] == {"detections": 3}
    assert conn.rows[run_id]["completed"]
    assert "completed_at = now()" in conn.statements[-1]
    assert conn.commits == 2


def test_finish_run_rejects_a_status_that_is_not_final() -> None:
    conn = FakeConn()
    run_id = start_run(conn, "skywatch.proximity", "0.1.0")
    for bad in ("RUNNING", "success", "DONE"):
        with pytest.raises(ValueError):
            finish_run(conn, run_id, status=bad, counts={})
    assert len(conn.statements) == 1  # only the start_run INSERT ever ran
    assert conn.rows[run_id]["status"] == "RUNNING"


def test_finish_run_unknown_run_id_is_an_error() -> None:
    conn = FakeConn()
    with pytest.raises(LookupError):
        finish_run(conn, str(uuid.uuid4()), status="SUCCESS", counts={})
    assert conn.commits == 0


def test_running_the_detector_leaves_one_detector_runs_row() -> None:
    """The ticket's done-when: one run of the real detector, one row."""
    conn = FakeConn()
    detector = ProximityDetector()
    run_id = start_run(conn, detector.detector_id, detector.detector_version, window=(T0, T1))
    detections = detector.detect_observations(load_observations("proximity_head_on.json"))
    finish_run(conn, run_id, status="SUCCESS", counts={"detections": len(detections)})

    assert len(conn.rows) == 1
    row = conn.rows[run_id]
    assert row["detector_id"] == "skywatch.proximity"
    assert row["status"] == "SUCCESS"
    assert row["counts"] == {"detections": 1}


def test_sql_only_uses_columns_the_migration_creates() -> None:
    """Guard against the code and db/schema/006 drifting apart (no live DB needed)."""
    ddl = MIGRATION.read_text(encoding="utf-8")
    body = re.search(r"CREATE TABLE IF NOT EXISTS public\.detector_runs \((.*?)\n\);", ddl, re.S)
    assert body is not None
    lines = [ln.strip() for ln in body.group(1).splitlines()]
    columns = {ln.split()[0] for ln in lines if ln and not ln.startswith("--")}

    conn = FakeConn()
    run_id = start_run(conn, "skywatch.proximity", "0.1.0", window=(T0, T1))
    finish_run(conn, run_id, status="SUCCESS", counts={})
    insert, update = conn.statements
    used = set(re.search(r"\(([^)]*)\)", insert).group(1).replace("\n", " ").split(","))  # type: ignore[union-attr]
    used = {c.strip() for c in used}
    used |= set(re.findall(r"(\w+) = ", update))
    assert used <= columns, used - columns
