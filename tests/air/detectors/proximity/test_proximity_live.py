"""Proximity's live table: extra_columns + 003_proximity_detections.sql. OWNER: Erik.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_live.py -q

The real-Postgres test runs only when SKYWATCH_TEST_DSN is set (e.g. the local
`docker compose up -d db`). It applies the actual migration inside a
transaction, writes through persist(), checks the row, and rolls everything
back, so it never leaves data behind.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from air.detectors.proximity import ProximityDetector
from air.detectors.proximity.live import TABLE, extra_columns
from air.live.persistence import PersistResult, dedup_key, persist
from tests.air.live.test_persistence import FakeDB
from tests.conftest import load_observations

MIGRATION = Path(__file__).resolve().parents[4] / "db" / "schema" / "003_proximity_detections.sql"


def _detection():
    [d] = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))
    return d


def test_extra_columns_maps_a_pair():
    cols = extra_columns(_detection())
    assert cols["member_entity_ids"] == ["icao24:aaa001", "icao24:bbb002"]
    assert cols["predicted_horizontal_nm"] == pytest.approx(0.2, abs=1e-3)
    assert cols["predicted_vertical_ft"] == pytest.approx(200.0)
    assert cols["t_cpa_seconds"] == pytest.approx(58.0, abs=0.1)


def test_member_ids_are_sorted_whichever_aircraft_is_listed_first():
    det = _detection()
    det.entities_involved = list(reversed(det.entities_involved))
    assert extra_columns(det)["member_entity_ids"] == ["icao24:aaa001", "icao24:bbb002"]


def test_missing_closest_approach_evidence_abstains():
    det = _detection()
    det.evidence = [e for e in det.evidence if e.evidence_type != "predicted_closest_approach"]
    cols = extra_columns(det)
    assert cols["member_entity_ids"] == ["icao24:aaa001", "icao24:bbb002"]
    assert cols["predicted_horizontal_nm"] is None
    assert cols["predicted_vertical_ft"] is None
    assert cols["t_cpa_seconds"] is None


def test_extra_columns_match_the_migration():
    # Every key extra_columns returns must be a column in 003, or persist fails live.
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in extra_columns(_detection()):
        assert f"\n    {col} " in sql, col


def test_persist_writes_a_proximity_row():
    db, det = FakeDB(), _detection()
    assert persist(db, TABLE, [det], extra_columns=extra_columns) == PersistResult(inserted=1)
    assert persist(db, TABLE, [det], extra_columns=extra_columns) == PersistResult(updated=1)
    [row] = db.tables[TABLE].values()
    assert row["severity"] == "HIGH"
    assert row["member_entity_ids"] == ["icao24:aaa001", "icao24:bbb002"]
    assert row["t_cpa_seconds"] == pytest.approx(58.0, abs=0.1)


DSN = os.environ.get("SKYWATCH_TEST_DSN")


@pytest.mark.skipif(not DSN, reason="set SKYWATCH_TEST_DSN to run against Postgres")
def test_real_postgres_migration_and_persist():
    psycopg = pytest.importorskip("psycopg")
    det = _detection()
    with psycopg.connect(DSN) as conn:
        try:
            conn.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent: IF NOT EXISTS
            assert persist(conn, TABLE, [det], extra_columns=extra_columns).inserted == 1
            assert persist(conn, TABLE, [det], extra_columns=extra_columns).updated == 1
            row = conn.execute(
                "SELECT count(*), min(member_entity_ids::text), min(predicted_vertical_ft),"
                " bool_and(position IS NOT NULL) FROM proximity_detections WHERE dedup_key = %s",
                [dedup_key(det)],
            ).fetchone()
            assert row == (1, "{icao24:aaa001,icao24:bbb002}", 200.0, True)
        finally:
            conn.rollback()  # leave the local DB exactly as it was
