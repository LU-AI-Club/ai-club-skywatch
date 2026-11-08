"""Integration test for the Spine A query (A2) against a real database.

Skipped unless ``SKYWATCH_TEST_DSN`` is set, because the repo rule is that a
PR's tests run on fixtures with no live services. This one cannot: the whole
point of it is to prove the SQL is valid SQL and that PostGIS gives back what
we think it does, neither of which a fake connection can tell us.

Run it locally with the compose database up::

    docker compose up -d db
    SKYWATCH_TEST_DSN=postgresql://skywatch:skywatch@localhost:5432/skywatch \
        python -m pytest tests/air/live/test_observations_reader_sql.py -q

Seed it first with ``python scripts/load_observations_csv.py --limit 20000``.

The mapping is tested separately and without a database, in the A4 tests --
that split is why this file can afford to be skipped most of the time.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest

from air.live.observations_reader import _select_rows

DSN = os.environ.get("SKYWATCH_TEST_DSN")

pytestmark = pytest.mark.skipif(
    not DSN, reason="set SKYWATCH_TEST_DSN to run the live-database tests"
)

# Every ADS-B field some detector needs. Not all of them are ours: squawk
# carries the 7500/7600/7700 emergency codes the no-fly-zone detector reads,
# and emitter_category and on_ground matter to the others. A field quietly
# missing from payload blinds their detector, not ours, which is exactly the
# failure this list exists to catch.
PAYLOAD_FIELDS = (
    "altitude_ft",
    "alt_geom_ft",
    "vertical_rate_fpm",
    "nic",
    "nacp",
    "squawk",
    "callsign",
    "emitter_category",
    "on_ground",
)


@pytest.fixture(scope="module")
def conn():
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(DSN) as connection:
        yield connection


@pytest.fixture(scope="module")
def span(conn):
    """The time range the seeded data actually covers."""
    with conn.cursor() as cur:
        cur.execute("SELECT min(observed_at), max(observed_at) FROM observations")
        low, high = cur.fetchone()
    if low is None:
        pytest.skip("observations is empty; seed it with load_observations_csv.py")
    return low, high


def test_the_query_runs_and_returns_rows(conn, span):
    low, _ = span
    rows = _select_rows(conn, start=low, end=low + timedelta(seconds=60), domain="air")
    assert rows, "a 60 s window of seeded data should not be empty"


def test_every_column_the_mapper_expects_is_present(conn, span):
    """The mapper reads these by name; a renamed column must fail here."""
    low, _ = span
    row = _select_rows(conn, start=low, end=low + timedelta(seconds=60), domain="air")[0]
    assert set(row) == {
        "entity_id",
        "observed_at",
        "latitude",
        "longitude",
        "sog",
        "cog",
        "payload",
        "raw_record_ref",
    }


def test_latitude_and_longitude_are_not_swapped(conn, span):
    """ST_Y is latitude and ST_X is longitude -- easy to transpose silently.

    The capture is around Lynchburg, Virginia: northern hemisphere, western
    hemisphere. Swapped values would still be valid floats, so the only thing
    that catches it is checking they land where the aircraft actually were.
    """
    low, _ = span
    rows = _select_rows(conn, start=low, end=low + timedelta(seconds=60), domain="air")
    assert all(20.0 < r["latitude"] < 60.0 for r in rows)
    assert all(-110.0 < r["longitude"] < -60.0 for r in rows)


def test_the_payload_carries_every_detectors_fields(conn, span):
    """Including the ones spoofing itself does not use."""
    low, _ = span
    rows = _select_rows(conn, start=low, end=low + timedelta(seconds=60), domain="air")
    seen: set[str] = set()
    for row in rows:
        seen.update(k for k, v in row["payload"].items() if v is not None)
    missing = [f for f in PAYLOAD_FIELDS if f not in seen]
    assert not missing, f"no row in this window reported: {missing}"


def test_the_window_is_half_open(conn, span):
    """[start, end): a report exactly on `end` belongs to the next window.

    Consecutive windows would otherwise both claim it, and the rolling runner
    reads back-to-back windows all day.
    """
    low, _ = span
    with conn.cursor() as cur:
        cur.execute(
            "SELECT observed_at FROM observations WHERE domain = 'air' "
            "ORDER BY observed_at OFFSET 50 LIMIT 1"
        )
        boundary = cur.fetchone()[0]

    before = _select_rows(conn, start=low, end=boundary, domain="air")
    assert all(r["observed_at"] < boundary for r in before)

    after = _select_rows(
        conn, start=boundary, end=boundary + timedelta(seconds=1), domain="air"
    )
    assert all(r["observed_at"] >= boundary for r in after)


def test_an_empty_window_returns_nothing(conn, span):
    """A quiet minute is not an error."""
    _, high = span
    assert _select_rows(conn, start=high, end=high, domain="air") == []


def test_another_domain_is_not_read(conn, span):
    """The table is shared with maritime; we must not pick up vessels."""
    low, _ = span
    rows = _select_rows(
        conn, start=low, end=low + timedelta(seconds=60), domain="sea"
    )
    assert rows == []


def test_rows_arrive_grouped_by_aircraft_in_time_order(conn, span):
    """Not cosmetic: every physics rule compares consecutive reports.

    The feature stage groups by aircraft and walks pairs in time order, so the
    query sorting this way is what makes that cheap.
    """
    low, _ = span
    rows = _select_rows(conn, start=low, end=low + timedelta(seconds=60), domain="air")
    keys = [(r["entity_id"], r["observed_at"]) for r in rows]
    assert keys == sorted(keys)
