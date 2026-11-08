"""Does ``db/schema/002_spoofing_detections.sql`` actually apply? -- ticket T3.

Skipped unless ``SKYWATCH_TEST_DSN`` is set, for the same reason as
``tests/air/live/test_observations_reader_sql.py``: a PR's tests run on
fixtures with no live services, and this one cannot. The whole point is that
PostgreSQL accepts the file, which only PostgreSQL can tell us.

Run it with the compose database up::

    docker compose up -d db
    SKYWATCH_TEST_DSN=postgresql://skywatch:skywatch@localhost:5432/skywatch \
        python -m pytest tests/db -q

If 5432 is already taken -- another project's Postgres, which is common --
publish on a different port and say so in the DSN; the two have to match::

    POSTGRES_PORT=55432 docker compose up -d db
    SKYWATCH_TEST_DSN=postgresql://skywatch:skywatch@localhost:55432/skywatch \
        python -m pytest tests/db -q

**How it avoids touching real data.** Every test runs the migration inside a
transaction that is always rolled back, never committed. PostgreSQL has fully
transactional DDL, so the table these tests create and write to does not
survive the rollback; nothing is left behind and an existing table is restored
untouched even if a test fails part way through. The file is executed verbatim
rather than paraphrased, because a test against a retyped copy of a migration
proves nothing about the migration.

Two guards back that up: the DSN must point at a local database, and the
connection is never committed. Both are asserted rather than assumed.

**Why T3 is worth automating at all.** It was written as "verify it loads",
a thing you do once by hand and then believe forever. The failure it guards
against is not someone breaking the ``CREATE TABLE`` -- it is the table
drifting away from what ``air/live/persistence.py`` fills generically from
``Detection.to_dict()`` for all three detectors. A column renamed here and the
persistence layer starts failing on insert for everyone, so the shared column
set is checked by name.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "db" / "schema" / "002_spoofing_detections.sql"
TABLE = "spoofing_detections"

DSN = os.environ.get("SKYWATCH_TEST_DSN")

pytestmark = pytest.mark.skipif(
    not DSN, reason="set SKYWATCH_TEST_DSN to run the live-database tests"
)

# Local hosts only. These tests roll back, but they also DROP the table inside
# that transaction, and the cost of being wrong about which database the DSN
# names is other people's data. Cheap to check, so it is checked.
LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "@/", "db")

# The 24 shared columns from docs/live_integration/DETECTION_TABLE_COLUMNS.md,
# plus the generated `position`. air/live/persistence.py fills these
# generically for all three detectors, so this list is a cross-team contract
# and not a restatement of the file under test.
SHARED_COLUMNS = {
    "detection_id",
    "dedup_key",
    "detector_id",
    "detector_version",
    "detection_type",
    "severity",
    "confidence",
    "entity_id",
    "entities_involved",
    "temporal_bounds_start",
    "temporal_bounds_end",
    "latitude",
    "longitude",
    "position",
    "evidence",
    "geospatial_context",
    "provenance",
    "tags",
    "metadata",
    "raw_detection",
    "detection_run_id",
    "first_detected_at",
    "last_detected_at",
    "created_at",
    "updated_at",
}


def test_the_dsn_points_at_a_local_database() -> None:
    """A precondition of every test below, asserted once and by name."""
    assert DSN is not None
    assert any(host in DSN for host in LOCAL_HOSTS), (
        "refusing to run DDL against a non-local DSN; these tests drop and "
        "recreate the detections table inside a rolled-back transaction"
    )


@pytest.fixture
def applied(request):
    """Apply the migration in a transaction and roll it back afterwards.

    Yields an open cursor with the table freshly created from the real file.
    The drop is what makes the ``CREATE TABLE IF NOT EXISTS`` meaningful --
    without it, a table left over from ``docker compose up`` would make every
    assertion below pass without the file having been read at all.
    """
    psycopg = pytest.importorskip("psycopg")
    if not any(host in (DSN or "") for host in LOCAL_HOSTS):
        pytest.skip("non-local DSN; see test_the_dsn_points_at_a_local_database")

    connection = psycopg.connect(DSN, autocommit=False)
    try:
        with connection.cursor() as cur:
            cur.execute(f"DROP TABLE IF EXISTS public.{TABLE} CASCADE")
            cur.execute(MIGRATION.read_text(encoding="utf-8"))
            yield cur
    finally:
        # Never committed. The table, and anything written to it, goes away.
        connection.rollback()
        connection.close()


def _columns(cur) -> dict[str, str]:
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (TABLE,),
    )
    return {name: data_type for name, data_type in cur.fetchall()}


def test_the_migration_applies(applied) -> None:
    """The headline of the ticket: PostgreSQL accepts the file."""
    assert _columns(applied), f"{TABLE} does not exist after applying the migration"


def test_every_shared_column_is_present(applied) -> None:
    """The cross-team contract: persistence.py fills these by name.

    A column renamed or dropped here does not break spoofing in isolation --
    it breaks the shared writer, and therefore the other two detectors too.
    """
    missing = SHARED_COLUMNS - set(_columns(applied))
    assert not missing, f"missing shared columns: {sorted(missing)}"


def test_there_are_no_detector_specific_columns(applied) -> None:
    """Deliberate, and worth pinning so it is not quietly undone.

    A spoofing finding is about one aircraft, and the part that varies between
    rules -- which gate fired, the measured value against its threshold, the
    feature records behind it -- already lives in `evidence` and `metadata`.
    Flattening those into columns would mean a migration every time a rule is
    added, and `metadata` has a GIN index precisely so that is unnecessary.
    """
    extra = set(_columns(applied)) - SHARED_COLUMNS
    assert not extra, f"unexpected detector-specific columns: {sorted(extra)}"


def _row(**overrides) -> dict:
    row = {
        "detection_id": str(uuid4()),
        "dedup_key": "skywatch.spoofing|0.1.0|speed_delta|aircraft:a1b2c3|2026-11-03T14:05:00Z",
        "detector_id": "skywatch.spoofing",
        "detector_version": "0.1.0",
        "detection_type": "speed_delta",
        "severity": "MEDIUM",
        "confidence": 0.72,
        "entity_id": "aircraft:a1b2c3",
        "temporal_bounds_start": datetime(2026, 11, 3, 14, 5, tzinfo=timezone.utc),
        "temporal_bounds_end": datetime(2026, 11, 3, 14, 6, tzinfo=timezone.utc),
        "latitude": 37.3267,
        "longitude": -79.2000,
    }
    row.update(overrides)
    return row


def _insert(cur, row: dict) -> None:
    columns = ", ".join(row)
    placeholders = ", ".join(f"%({name})s" for name in row)
    cur.execute(
        f"INSERT INTO public.{TABLE} ({columns}) VALUES ({placeholders})", row
    )


def test_a_detection_can_be_written(applied) -> None:
    _insert(applied, _row())
    applied.execute(f"SELECT count(*) FROM public.{TABLE}")
    assert applied.fetchone()[0] == 1


def test_the_position_column_is_generated_from_latitude_and_longitude(applied) -> None:
    """The map filters on `position`; nothing writes it.

    If it were an ordinary column the writer would have to build the geometry,
    and every team would build it slightly differently. ST_MakePoint takes
    longitude first, which is the transposition this asserts against.
    """
    _insert(applied, _row())
    applied.execute(
        f"SELECT ST_Y(position::geometry), ST_X(position::geometry) FROM public.{TABLE}"
    )
    latitude, longitude = applied.fetchone()
    assert latitude == pytest.approx(37.3267)
    assert longitude == pytest.approx(-79.2000)


def test_position_is_null_when_there_is_no_position(applied) -> None:
    """An identity finding has no coordinates, and must still be storable.

    identity_drift_v1 is about a callsign disagreeing with a registry block;
    there is no single point to put on a map. A NOT NULL here would have made
    that whole class of finding unwritable.
    """
    _insert(applied, _row(latitude=None, longitude=None))
    applied.execute(f"SELECT position FROM public.{TABLE}")
    assert applied.fetchone()[0] is None


def test_the_same_finding_twice_updates_in_place(applied) -> None:
    """The reason `dedup_key` is unique, and the thing T3 really has to prove.

    The live runner re-reads an overlapping window every tick, so the same
    finding genuinely does arrive again and again. Without the upsert the table
    grows one row per tick per finding and the map shows the same aircraft
    forty times.
    """
    first = _row(confidence=0.72)
    _insert(applied, first)

    second = _row(
        detection_id=str(uuid4()),  # a new run; same finding
        dedup_key=first["dedup_key"],
        confidence=0.81,
    )
    columns = ", ".join(second)
    placeholders = ", ".join(f"%({name})s" for name in second)
    applied.execute(
        f"""
        INSERT INTO public.{TABLE} ({columns}) VALUES ({placeholders})
        ON CONFLICT (dedup_key) DO UPDATE SET
            confidence = EXCLUDED.confidence,
            last_detected_at = now(),
            updated_at = now()
        """,
        second,
    )

    applied.execute(f"SELECT count(*), max(confidence) FROM public.{TABLE}")
    count, confidence = applied.fetchone()
    assert count == 1, "the second arrival of one finding must not add a row"
    assert confidence == pytest.approx(0.81), "it must update in place"


def test_a_duplicate_dedup_key_without_an_upsert_is_refused(applied) -> None:
    """The constraint is real, not decorative.

    Asserted separately from the upsert because an upsert also succeeds on a
    table with no unique constraint at all -- it just silently stops
    deduplicating.
    """
    psycopg = pytest.importorskip("psycopg")
    row = _row()
    _insert(applied, row)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert(applied, _row(detection_id=str(uuid4()), dedup_key=row["dedup_key"]))


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"confidence": 1.4}, "confidence above 1"),
        ({"confidence": -0.1}, "confidence below 0"),
        (
            {
                "temporal_bounds_start": datetime(2026, 11, 3, 14, 6, tzinfo=timezone.utc),
                "temporal_bounds_end": datetime(2026, 11, 3, 14, 5, tzinfo=timezone.utc),
            },
            "window ending before it starts",
        ),
    ],
    ids=["confidence_high", "confidence_low", "backwards_window"],
)
def test_the_check_constraints_reject_impossible_rows(applied, overrides, reason) -> None:
    """Garbage in the detections table is worse than a failed insert.

    A confidence of 1.4 would sort above every real finding in the API's
    default listing, and a backwards window would silently drop out of any
    time-range query. Better to fail loudly at the boundary.
    """
    psycopg = pytest.importorskip("psycopg")
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert(applied, _row(**overrides))


def test_an_open_ended_window_is_allowed(applied) -> None:
    """A finding that is still happening has no end yet.

    The temporal-order constraint has to admit NULL, or a live finding could
    not be written until it was over.
    """
    _insert(applied, _row(temporal_bounds_end=None))
    applied.execute(f"SELECT temporal_bounds_end FROM public.{TABLE}")
    assert applied.fetchone()[0] is None


def test_the_indexes_the_queries_rely_on_exist(applied) -> None:
    """Each one answers a question someone actually asks.

    entity_time: "what has this aircraft done", newest first.
    last_detected_at: "what is active now", the API's default listing.
    metadata_gin: filter by gate or score without a migration.
    position_gist: "what fired inside this box", for the map.
    """
    applied.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = %s",
        (TABLE,),
    )
    indexes = {name for (name,) in applied.fetchall()}
    for suffix in (
        "entity_time",
        "last_detected_at",
        "metadata_gin",
        "position_gist",
    ):
        assert any(
            name.endswith(suffix) for name in indexes
        ), f"no index for {suffix}; have {sorted(indexes)}"


def test_the_jsonb_columns_default_rather_than_requiring_a_value(applied) -> None:
    """persistence.py omits a key it has nothing for, and must not fail.

    Every one of these is NOT NULL, so without the defaults a detection with
    no tags would be unwritable.
    """
    _insert(applied, _row())
    applied.execute(
        f"SELECT entities_involved, evidence, geospatial_context, provenance, "
        f"tags, metadata, raw_detection FROM public.{TABLE}"
    )
    assert applied.fetchone() == ([], [], {}, {}, [], {}, {})


def test_applying_the_migration_twice_is_not_an_error(applied) -> None:
    """Every statement is IF NOT EXISTS, so a re-run on a live database is safe.

    This is what lets the compose init directory and a manual `psql -f` both
    be correct, and it is the difference between a migration and a one-shot
    script.
    """
    applied.execute(MIGRATION.read_text(encoding="utf-8"))
    assert _columns(applied)


def test_nothing_was_committed() -> None:
    """The safety claim in this module's docstring, actually checked.

    Opens its own connection after the others have rolled back. If any test
    above had committed, the rows it wrote would be visible here.
    """
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DSN) as connection:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT to_regclass(%s) IS NOT NULL", (f"public.{TABLE}",)
            )
            if not cur.fetchone()[0]:
                return  # no table outside the transactions: nothing leaked
            cur.execute(f"SELECT count(*) FROM public.{TABLE} WHERE detector_id = %s",
                        ("skywatch.spoofing",))
            assert cur.fetchone()[0] == 0, "a test leaked rows into the real table"
