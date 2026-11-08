"""Spine component A — read canonical observations as AdsbObservations.

OWNER: Spoofing team (see docs/live_integration/TEAM_SPOOFING.md).

This is the single source of truth for turning rows in the `observations` table
into the detectors' input contract. It owns the `payload` JSON parsing so no two
teams parse it differently. No other team touches SQL or `payload` here — they
call `read_window`.

The signature of `read_window` is FROZEN (the contract the runner and tests
build against). Do not change it without announcing it to the Proximity (B) and
No-Fly-Zone (C) teams, who import it.

Three pieces, split so each is testable on its own:

    _select_rows           SQL: the windowed query          (A2, here)
    payload.observation_from_row    one row -> one object   (A3a)
    row_validation.unusable_reason  which rows to skip      (A3b)

**This reader serves all three detectors, not just spoofing.** It therefore
pulls every ADS-B field any of them needs, including ones spoofing itself
barely uses — `squawk` carries the emergency codes (7500/7600/7700) the
no-fly-zone detector reads, and dropping it here would silently blind that
detector rather than ours.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from air.live.payload import observation_from_row
from air.models.observation import AdsbObservation

__all__ = ["read_window", "SELECT_WINDOW_SQL"]


# Half-open on observed_at so consecutive windows neither drop a report nor
# count one twice: [start, end). The rolling runner overlaps windows on
# purpose, and dedup on the detection side absorbs that — but a report landing
# in two windows *here* would still be wasted work.
#
# latitude/longitude come out of the GEOGRAPHY column in SQL rather than being
# parsed in Python: PostGIS already knows how, and the alternative is decoding
# WKB by hand. ST_Y is latitude, ST_X is longitude — easy to swap by accident,
# so the parity test (A4d) is what proves this right.
#
# The ORDER BY matches the (entity_id, observed_at) index the plan calls for,
# and it is not cosmetic: every physics rule compares consecutive reports of
# one aircraft, so rows arriving grouped and in time order is what the feature
# stage expects.
SELECT_WINDOW_SQL = """
SELECT
    entity_id,
    observed_at,
    ST_Y(location::geometry) AS latitude,
    ST_X(location::geometry) AS longitude,
    sog,
    cog,
    payload,
    raw_record_ref
FROM observations
WHERE domain = %(domain)s
  AND observed_at >= %(start)s
  AND observed_at <  %(end)s
ORDER BY entity_id, observed_at
"""


def _select_rows(
    conn: Any, *, start: datetime, end: datetime, domain: str
) -> list[dict[str, Any]]:
    """Run the windowed query and return plain dicts, one per row.

    Separated from ``read_window`` so the SQL can be tested against a real
    database without the mapping, and the mapping tested without a database.
    Returns dicts rather than driver tuples so nothing downstream depends on
    column order.
    """
    with conn.cursor() as cur:
        cur.execute(SELECT_WINDOW_SQL, {"start": start, "end": end, "domain": domain})
        columns = [c.name for c in cur.description]
        return [dict(zip(columns, values)) for values in cur.fetchall()]


def read_window(
    conn: Any,
    *,
    start: datetime,
    end: datetime,
    domain: str = "air",
) -> list[AdsbObservation]:
    """Return the observations in ``[start, end)`` as ``AdsbObservation``s.

    Parameters
    ----------
    conn:
        A live database connection (psycopg). Passed in by the runner; never
        opened here.
    start, end:
        Window bounds, tz-aware UTC. Half-open: ``start`` inclusive, ``end``
        exclusive.
    domain:
        Observation domain to read; ``"air"`` for ADS-B.

    Rows that cannot form a valid ``AdsbObservation`` are skipped rather than
    guessed at, per the repo rule — ``observation_from_row`` returns ``None``
    for those. A window with nothing in it returns ``[]``; that is a quiet
    minute, not an error.

    Pure read: no writes, no detector logic.
    """
    observations: list[AdsbObservation] = []
    for row in _select_rows(conn, start=start, end=end, domain=domain):
        observation = observation_from_row(row)
        if observation is not None:
            observations.append(observation)
    return observations
