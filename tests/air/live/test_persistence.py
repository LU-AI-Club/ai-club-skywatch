"""Spine B: persist() writes detections idempotently. OWNER: Erik (Proximity team).

Run just these:  pytest tests/air/live/test_persistence.py -q

Two layers:
  * Fake-connection tests always run (CI has no database). The fake keeps rows
    keyed on dedup_key and applies the same insert-or-update rule Postgres does.
  * test_real_postgres_* run only when SKYWATCH_TEST_DSN points at a database
    (e.g. the local `docker compose up -d db`); otherwise they skip. They prove
    the SQL itself against real Postgres.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

import pytest

from air.detectors.proximity import ProximityDetector
from air.live.persistence import PersistResult, dedup_key, persist
from tests.conftest import load_observations

TABLE = "proximity_detections"


def _detection():
    [d] = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))
    return d


def _extra(det) -> dict[str, Any]:
    ev = next(e for e in det.evidence if e.evidence_type == "predicted_closest_approach")
    return {
        "member_entity_ids": [e.entity_id for e in det.entities_involved],
        "predicted_horizontal_nm": ev.metadata["predicted_horizontal_nm"],
        "predicted_vertical_ft": ev.metadata["predicted_vertical_ft"],
        "t_cpa_seconds": ev.metadata["t_cpa_s"],
    }


# --- A fake psycopg connection that behaves like ON CONFLICT (dedup_key) ------
class FakeCursor:
    def __init__(self, db: FakeDB) -> None:
        self.db = db
        self._last: tuple[bool] | None = None

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        pass

    def execute(self, sql: str, params: list[Any]) -> None:
        self.db.statements.append(sql)
        m = re.match(r"INSERT INTO (\w+) \(([^)]*)\) VALUES", sql)
        assert m, sql
        assert "ON CONFLICT (dedup_key) DO UPDATE SET" in sql
        table, columns = m.group(1), [c.strip() for c in m.group(2).split(",")]
        row = dict(zip(columns, params, strict=True))
        rows = self.db.tables.setdefault(table, {})
        key = row["dedup_key"]
        if key not in rows:
            first = self.db.tick()
            rows[key] = {**row, "first_detected_at": first, "last_detected_at": first,
                         "updated_at": None}
            self._last = (True,)
        else:
            kept = {c: rows[key][c] for c in ("detection_id", "dedup_key", "first_detected_at")}
            rows[key] = {**rows[key], **row, **kept, "last_detected_at": self.db.tick(),
                         "updated_at": self.db.now}
            self._last = (False,)

    def fetchone(self) -> tuple[bool] | None:
        return self._last


class FakeDB:
    def __init__(self) -> None:
        self.tables: dict[str, dict[str, dict[str, Any]]] = {}
        self.statements: list[str] = []
        self.now = 0

    def tick(self) -> int:
        self.now += 1
        return self.now

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)


# --- Always-on tests ------------------------------------------------------------
def test_same_detection_twice_is_one_insert_then_one_update():
    db, det = FakeDB(), _detection()
    first = persist(db, TABLE, [det])
    second = persist(db, TABLE, [det])
    assert first == PersistResult(inserted=1)
    assert second == PersistResult(updated=1)
    assert len(db.tables[TABLE]) == 1


def test_update_keeps_first_seen_and_bumps_last_seen():
    db, det = FakeDB(), _detection()
    persist(db, TABLE, [det])
    [before] = db.tables[TABLE].values()
    first_seen, last_seen = before["first_detected_at"], before["last_detected_at"]
    persist(db, TABLE, [det])
    [after] = db.tables[TABLE].values()
    assert after["first_detected_at"] == first_seen
    assert after["last_detected_at"] > last_seen
    assert after["updated_at"] is not None


def test_a_rerun_of_the_detector_updates_instead_of_duplicating():
    # A fresh detector run makes a NEW Detection object with a new random
    # detection_id -- the dedup_key is what makes it the same row.
    db = FakeDB()
    a, b = _detection(), _detection()
    assert a.detection_id != b.detection_id and dedup_key(a) == dedup_key(b)
    assert persist(db, TABLE, [a, b]) == PersistResult(inserted=1, updated=1)
    [row] = db.tables[TABLE].values()
    assert row["detection_id"] == str(a.detection_id)  # primary key never changes


def test_shared_columns_filled_from_to_dict():
    db, det = FakeDB(), _detection()
    persist(db, TABLE, [det], run_id="11111111-1111-1111-1111-111111111111")
    [row] = db.tables[TABLE].values()
    d = det.to_dict()
    assert row["dedup_key"] == dedup_key(det)
    assert (row["detector_id"], row["detector_version"]) == ("skywatch.proximity", "0.1.0")
    assert (row["detection_type"], row["severity"]) == ("predicted_proximity", "HIGH")
    assert row["confidence"] == pytest.approx(d["confidence"])
    assert row["entity_id"] == "aircraft:aaa001"
    assert row["temporal_bounds_start"] == d["temporal_bounds"]["start_time"]
    assert row["temporal_bounds_end"] == d["temporal_bounds"]["end_time"]
    assert row["latitude"] == pytest.approx(37.4154655)
    assert row["longitude"] == pytest.approx(-79.1422004)
    assert row["detection_run_id"] == "11111111-1111-1111-1111-111111111111"
    # JSONB columns go over the wire as JSON text; raw_detection is lossless.
    assert json.loads(row["raw_detection"]) == json.loads(json.dumps(d, default=str))
    assert len(json.loads(row["entities_involved"])) == 2
    assert json.loads(row["metadata"])["explanation_facts"]


def test_extra_columns_hook_is_merged():
    db, det = FakeDB(), _detection()
    persist(db, TABLE, [det], extra_columns=_extra)
    [row] = db.tables[TABLE].values()
    assert row["member_entity_ids"] == ["aircraft:aaa001", "aircraft:bbb002"]
    assert row["predicted_horizontal_nm"] == pytest.approx(0.2, abs=1e-3)
    assert row["predicted_vertical_ft"] == pytest.approx(200.0)
    assert row["t_cpa_seconds"] == pytest.approx(58.0, abs=0.1)


def test_extra_columns_may_not_overwrite_shared_ones():
    with pytest.raises(ValueError, match="severity"):
        persist(FakeDB(), TABLE, [_detection()], extra_columns=lambda d: {"severity": "LOW"})


def test_unsafe_table_or_column_names_are_rejected():
    with pytest.raises(ValueError):
        persist(FakeDB(), "proximity_detections; DROP TABLE x", [_detection()])
    with pytest.raises(ValueError):
        persist(FakeDB(), TABLE, [_detection()], extra_columns=lambda d: {"bad name": 1})


def test_detection_without_entities_is_skipped_not_guessed():
    det = _detection()
    det.entities_involved = []
    db = FakeDB()
    assert persist(db, TABLE, [det]) == PersistResult(skipped=1)
    assert db.statements == []


def test_nothing_to_write_is_a_no_op():
    db = FakeDB()
    assert persist(db, TABLE, []) == PersistResult()
    assert db.statements == []


# --- Real Postgres (skipped unless SKYWATCH_TEST_DSN is set) ------------------
DSN = os.environ.get("SKYWATCH_TEST_DSN")
needs_db = pytest.mark.skipif(not DSN, reason="set SKYWATCH_TEST_DSN to run against Postgres")

# Shared columns from DETECTION_TABLE_COLUMNS.md (minus the PostGIS `position`
# column, so this runs on any Postgres) plus proximity's extras. TEMP: the
# table vanishes with the connection and never touches real data.
_TEMP_TABLE = """
CREATE TEMP TABLE proximity_detections_test (
    detection_id UUID PRIMARY KEY, dedup_key TEXT NOT NULL UNIQUE,
    detector_id TEXT NOT NULL, detector_version TEXT NOT NULL, detection_type TEXT NOT NULL,
    severity TEXT NOT NULL, confidence DOUBLE PRECISION NOT NULL, entity_id TEXT NOT NULL,
    entities_involved JSONB NOT NULL DEFAULT '[]', temporal_bounds_start TIMESTAMPTZ NOT NULL,
    temporal_bounds_end TIMESTAMPTZ, latitude DOUBLE PRECISION, longitude DOUBLE PRECISION,
    evidence JSONB NOT NULL DEFAULT '[]', geospatial_context JSONB NOT NULL DEFAULT '{}',
    provenance JSONB NOT NULL DEFAULT '{}', tags JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}', raw_detection JSONB NOT NULL DEFAULT '{}',
    detection_run_id UUID,
    first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ,
    member_entity_ids TEXT[], predicted_horizontal_nm DOUBLE PRECISION,
    predicted_vertical_ft DOUBLE PRECISION, t_cpa_seconds DOUBLE PRECISION
)
"""


@pytest.fixture
def pg():
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DSN) as conn:
        conn.execute(_TEMP_TABLE)
        conn.commit()  # TEMP table lives for the session, so it survives commits
        yield conn


@needs_db
def test_real_postgres_same_detection_twice_is_one_row(pg):
    det = _detection()
    write = lambda: persist(pg, "proximity_detections_test", [det], extra_columns=_extra)  # noqa: E731
    assert write() == PersistResult(inserted=1)
    pg.commit()
    assert write() == PersistResult(updated=1)
    rows = pg.execute(
        "SELECT count(*), min(severity), min(member_entity_ids::text),"
        " bool_and(updated_at IS NOT NULL), "
        "min(raw_detection->>'detector_id') FROM proximity_detections_test"
    ).fetchone()
    assert rows == (1, "HIGH", "{aircraft:aaa001,aircraft:bbb002}", True, "skywatch.proximity")


@needs_db
def test_real_postgres_rerun_keeps_first_seen(pg):
    a, b = _detection(), _detection()
    persist(pg, "proximity_detections_test", [a])
    pg.commit()  # the runner commits once per tick; now() is per-transaction
    persist(pg, "proximity_detections_test", [b])
    row = pg.execute(
        "SELECT count(*), min(detection_id::text), bool_and(last_detected_at > first_detected_at) "
        "FROM proximity_detections_test"
    ).fetchone()
    assert row == (1, str(a.detection_id), True)
