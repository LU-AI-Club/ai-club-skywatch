"""Fixture tests for ``read_window`` -- tickets A4b and A4c.

The companion to ``test_observations_reader_sql.py``. That one needs a real
database and so is skipped in CI; this one runs always, because it replaces the
database with a fake connection that hands back the rows from
``observation_rows.py`` exactly as psycopg would.

The split is deliberate. There are two independent ways the reader can be
wrong, and a test that needs Docker to run will not catch either on a Tuesday
afternoon:

* the **SQL** can be wrong -- a renamed column, latitude and longitude
  transposed, the window not half-open. Only a real database can say.
* the **mapping** can be wrong -- a payload field dropped, a bad row admitted,
  a good row discarded. That needs no database at all, which is what this file
  exploits.

A4b covers the rows that must come through and arrive intact. A4c covers the
rows that must not come through, and the empty window.

What is NOT tested here is whether the fake rows match the real table's shape;
that is what the skipped SQL test and the A4d parity test are for. A fixture
can only ever be as right as whoever last kept it up to date.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from observation_rows import (  # noqa: E402  (same directory; pytest puts it on sys.path)
    BROKEN_NO_ENTITY,
    BROKEN_NO_POSITION,
    BROKEN_NO_TIME,
    BROKEN_ROWS,
    EMPTY_ROWS,
    GOOD_ROW,
    MIXED_ROWS,
    PAYLOAD_ONLY_EXPECTED,
    PAYLOAD_ONLY_ROW,
    VALID_ROWS,
)

from air.live.observations_reader import SELECT_WINDOW_SQL, read_window
from air.live.row_validation import unusable_reason
from air.models.observation import AdsbObservation

WINDOW_START = datetime(2026, 11, 3, 14, 5, 0, tzinfo=timezone.utc)
WINDOW_END = WINDOW_START + timedelta(seconds=60)

# The columns SELECT_WINDOW_SQL projects, in order. The fake cursor reports
# these as its description, so a column added to the query without being added
# to the fixture surfaces here rather than as a None in production.
SELECTED_COLUMNS = (
    "entity_id",
    "observed_at",
    "latitude",
    "longitude",
    "sog",
    "cog",
    "payload",
    "raw_record_ref",
)


class _FakeColumn:
    """psycopg exposes column names as ``cur.description[i].name``."""

    def __init__(self, name: str) -> None:
        self.name = name


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.description = [_FakeColumn(name) for name in SELECTED_COLUMNS]
        self.executed: list[tuple[str, dict[str, Any]]] = []

    def execute(self, sql: str, params: dict[str, Any]) -> None:
        self.executed.append((sql, params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        # Tuples, not dicts: the driver returns positional rows, and
        # ``_select_rows`` is what zips them against the description. Handing
        # back dicts here would skip the part of the reader under test.
        # Indexed, not ``.get``: a fixture row missing a selected column is a
        # stale fixture, and it should fail loudly here rather than arrive
        # downstream as an indistinguishable None.
        return [tuple(row[name] for name in SELECTED_COLUMNS) for row in self._rows]

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


class _FakeConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_obj = _FakeCursor(rows)

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj


def _read(rows: list[dict[str, Any]], **kwargs: Any) -> list[AdsbObservation]:
    return read_window(
        _FakeConnection(rows), start=WINDOW_START, end=WINDOW_END, **kwargs
    )


def test_the_fake_cursor_projects_what_the_real_query_projects():
    """Keeps this file honest when the query changes.

    Everything below runs against SELECTED_COLUMNS rather than the real
    database, so if the SQL gains a column and this tuple does not, all of
    these tests keep passing while the reader loses a field. Parsing the
    select list is what ties the two together.
    """
    select_list = SELECT_WINDOW_SQL.split("SELECT", 1)[1].split("FROM", 1)[0]
    projected = [
        part.strip().split()[-1].lower()  # "ST_Y(...) AS latitude" -> "latitude"
        for part in select_list.split(",")
        if part.strip()
    ]
    assert projected == list(SELECTED_COLUMNS)


# --- A4b: the rows that must come through ------------------------------------
def test_a_good_row_becomes_one_observation():
    observations = _read([GOOD_ROW])
    assert len(observations) == 1
    assert isinstance(observations[0], AdsbObservation)


def test_the_typed_columns_land_on_the_right_fields():
    """``sog`` and ``cog`` are not named like their destinations.

    They come from the shared maritime-and-air schema, where they are speed and
    course over ground. Mapping them to the wrong pair of fields would leave
    every value populated and every physics rule wrong, which no type checker
    would notice.
    """
    observation = _read([GOOD_ROW])[0]
    assert observation.icao24 == "a1b2c3"
    assert observation.observed_at == GOOD_ROW["observed_at"]
    assert observation.latitude == pytest.approx(37.3267)
    assert observation.longitude == pytest.approx(-79.2000)
    assert observation.ground_speed_kt == pytest.approx(120.5)  # sog
    assert observation.track_deg == pytest.approx(275.0)  # cog
    assert observation.source_row_id == "data/lynchburg_adsb.csv:101"


def test_every_payload_field_survives_the_mapping():
    """These have no typed column, so a reader ignoring payload loses them.

    Listed one by one rather than compared as a dict, because the point of the
    ticket is that nothing silently goes missing -- and a dropped field reads
    downstream as "the feed did not report it", which is normal and therefore
    invisible.
    """
    observation = _read([GOOD_ROW])[0]
    assert observation.altitude_ft == 3500
    assert observation.alt_geom_ft == 3650
    assert observation.vertical_rate_fpm == 64
    assert observation.nic == 8
    assert observation.nacp == 9
    assert observation.squawk == "1200"
    assert observation.callsign == "N123AB"
    assert observation.emitter_category == "A1"
    assert observation.on_ground is False


def test_a_field_only_in_payload_is_kept_when_the_typed_column_is_empty():
    """The A4b case the ticket names: altitude and NIC live only in payload.

    This row has NULL ``sog`` and ``cog`` while its payload is full, so a
    reader that reached for the typed columns and gave up would return an
    observation that looks valid and is missing the altitude every vertical
    rule needs.
    """
    observation = _read([PAYLOAD_ONLY_ROW])[0]
    for field, expected in PAYLOAD_ONLY_EXPECTED.items():
        assert getattr(observation, field) == expected, field
    assert observation.ground_speed_kt is None
    assert observation.track_deg is None


def test_absent_is_none_and_not_zero():
    """Zero is a real speed; None means the feed did not say.

    The distinction is load-bearing: the detector reads a reported speed of 0
    as "stationary" and None as "no claim to check", and confusing the two
    invents disagreements with the measured value.
    """
    observation = _read([PAYLOAD_ONLY_ROW])[0]
    assert observation.ground_speed_kt is None
    assert observation.ground_speed_kt != 0


def test_several_rows_keep_the_order_the_query_returned():
    """The query orders by (entity_id, observed_at); the reader must not resort.

    Every physics rule walks consecutive reports of one aircraft, so the
    grouping is what makes the feature stage cheap. A reader that reordered
    rows would break no single mapping, only the pairing downstream.
    """
    observations = _read(VALID_ROWS)
    assert [o.icao24 for o in observations] == ["a1b2c3", "d4e5f6"]


def test_the_window_bounds_reach_the_query_unchanged():
    connection = _FakeConnection([GOOD_ROW])
    read_window(connection, start=WINDOW_START, end=WINDOW_END)

    _, params = connection.cursor_obj.executed[0]
    assert params == {"start": WINDOW_START, "end": WINDOW_END, "domain": "air"}


def test_the_domain_defaults_to_air_and_can_be_overridden():
    """The table is shared with maritime; reading vessels would be a real bug."""
    connection = _FakeConnection([])
    read_window(connection, start=WINDOW_START, end=WINDOW_END)
    assert connection.cursor_obj.executed[0][1]["domain"] == "air"

    connection = _FakeConnection([])
    read_window(connection, start=WINDOW_START, end=WINDOW_END, domain="sea")
    assert connection.cursor_obj.executed[0][1]["domain"] == "sea"


# --- A4c: the rows that must not come through --------------------------------
@pytest.mark.parametrize(
    "row,reason",
    [
        (BROKEN_NO_POSITION, "MISSING_POSITION"),
        (BROKEN_NO_TIME, "MISSING_TIME"),
        (BROKEN_NO_ENTITY, "MISSING_ENTITY"),
    ],
    ids=["no_position", "no_time", "no_entity"],
)
def test_an_unusable_row_is_skipped_for_the_reason_the_rules_name(row, reason):
    """Asserts the reason too, not just the skip.

    A row dropped for the wrong reason still produces the right count here,
    and the live per-reason counters are how anyone would notice the reader
    quietly discarding good data -- so the reason is part of the contract.
    """
    assert unusable_reason(row) == reason
    assert _read([row]) == []


def test_abstaining_never_guesses_a_position():
    """The specific failure the repo rule exists to prevent.

    A missing latitude is not (0, 0). Null Island is in the Gulf of Guinea, and
    an aircraft placed there would be a position jump of several thousand miles
    -- a HIGH-severity alert manufactured entirely by the reader.
    """
    assert _read([BROKEN_NO_POSITION]) == []


def test_one_bad_row_does_not_discard_the_good_rows_around_it():
    """Abstain means skip the row, not fail the window.

    Live, the reader sees whatever the feed produced. If a malformed record
    could take its window down with it, the detector would go blind for a
    minute at a time on exactly the noisy data it is there to watch.
    """
    observations = _read(MIXED_ROWS)
    assert [o.icao24 for o in observations] == ["a1b2c3", "d4e5f6"]
    assert len(observations) == len(MIXED_ROWS) - len(BROKEN_ROWS)


def test_a_window_of_nothing_but_bad_rows_returns_empty_rather_than_raising():
    assert _read(BROKEN_ROWS) == []


def test_an_empty_window_is_a_quiet_minute_not_an_error():
    """3am over Lynchburg. The runner polls through it and must not crash."""
    assert _read(EMPTY_ROWS) == []
