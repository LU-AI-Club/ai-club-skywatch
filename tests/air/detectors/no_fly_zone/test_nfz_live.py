"""No-fly-zone's live table: extra_columns + 004_no_fly_zone_detections.sql.

Run just these:  pytest tests/air/detectors/no_fly_zone/test_nfz_live.py -q

The real-Postgres test runs only when SKYWATCH_TEST_DSN is set (e.g. the local
`docker compose up -d db`). It applies the actual migration inside a
transaction, writes an open incursion and then its update through persist(),
checks the row, and rolls everything back, so it never leaves data behind.
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Before the detector imports, which need both: a machine without them should
# skip this file, not fail to collect it.
pytest.importorskip("shapely")
pytest.importorskip("h3")

from air.detectors.no_fly_zone import build_live_detector  # noqa: E402
from air.detectors.no_fly_zone.live import TABLE, extra_columns  # noqa: E402
from air.live.persistence import PersistResult, dedup_key, persist  # noqa: E402
from air.models.observation import AdsbObservation  # noqa: E402
from tests.air.live.test_persistence import FakeDB  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[4] / "db" / "schema" / "004_no_fly_zone_detections.sql"
_TS = datetime(2026, 9, 22, 20, 15, tzinfo=UTC)


def _obs(seconds: int) -> AdsbObservation:
    """An aircraft inside fixture zone P-901, below its ceiling."""
    return AdsbObservation(
        icao24="a1b2c3", observed_at=_TS + timedelta(seconds=seconds),
        latitude=37.425, longitude=-79.215, altitude_ft=4850.0, alt_geom_ft=5200.0,
        ground_speed_kt=186.7, track_deg=4.9, callsign="TEST123", squawk="1200",
        emitter_category="A3", nic=8, nacp=9, on_ground=False,
        source_row_id=f"test.csv:in{seconds}",
    )


def _open_incursion():
    [det] = build_live_detector().detect_observations([_obs(0), _obs(1)])
    return det


def test_extra_columns_names_the_zone():
    cols = extra_columns(_open_incursion())
    assert cols["zone_id"] == "P-901"
    assert cols["zone_type"] == "PROHIBITED"
    assert set(cols) == {"zone_id", "zone_name", "zone_type"}


def test_missing_zone_type_fails_loudly_not_in_postgres():
    det = _open_incursion()
    det.metadata["extras"] = {k: v for k, v in det.metadata["extras"].items() if k != "zone_type"}
    with pytest.raises(ValueError, match="zone_type"):
        extra_columns(det)


def test_missing_zone_name_is_allowed():
    det = _open_incursion()
    det.metadata["extras"] = {k: v for k, v in det.metadata["extras"].items() if k != "zone_name"}
    assert extra_columns(det)["zone_name"] is None


def test_extra_columns_match_the_migration():
    # Every key extra_columns returns must be a column in 004, or persist fails live.
    sql = MIGRATION.read_text(encoding="utf-8")
    for col in extra_columns(_open_incursion()):
        assert f"\n    {col} " in sql, col


def test_persist_writes_an_open_incursion_then_updates_it():
    detector = build_live_detector()
    db = FakeDB()
    [opened] = detector.detect_observations([_obs(0), _obs(1)])
    [grown] = detector.detect_observations([_obs(2), _obs(3)])
    assert dedup_key(opened) == dedup_key(grown)
    assert persist(db, TABLE, [opened], extra_columns=extra_columns) == PersistResult(inserted=1)
    assert persist(db, TABLE, [grown], extra_columns=extra_columns) == PersistResult(updated=1)
    [row] = db.tables[TABLE].values()
    assert (row["zone_id"], row["zone_type"]) == ("P-901", "PROHIBITED")
    assert row["entity_id"] == "aircraft:a1b2c3"


DSN = os.environ.get("SKYWATCH_TEST_DSN")


@pytest.mark.skipif(not DSN, reason="set SKYWATCH_TEST_DSN to run against Postgres")
def test_real_postgres_migration_and_persist():
    psycopg = pytest.importorskip("psycopg")
    detector = build_live_detector()
    [opened] = detector.detect_observations([_obs(0), _obs(1)])
    [closed] = detector.flush()
    with psycopg.connect(DSN) as conn:
        try:
            conn.execute(MIGRATION.read_text(encoding="utf-8"))  # idempotent: IF NOT EXISTS
            assert persist(conn, TABLE, [opened], extra_columns=extra_columns).inserted == 1
            assert persist(conn, TABLE, [closed], extra_columns=extra_columns).updated == 1
            row = conn.execute(
                "SELECT count(*), min(zone_id), min(zone_type), min(duration_seconds),"
                " bool_and(position IS NOT NULL) FROM no_fly_zone_detections"
                " WHERE dedup_key = %s",
                [dedup_key(closed)],
            ).fetchone()
            assert row == (1, "P-901", "PROHIBITED", 1.0, True)
        finally:
            conn.rollback()  # leave the local DB exactly as it was
