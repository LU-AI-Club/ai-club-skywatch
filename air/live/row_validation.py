"""Which `observations` rows can become an AdsbObservation, and which cannot.

OWNER: Daniel (ticket A3b) — see docs/live_integration/TEAM_SPOOFING.md.

Split out of the mapping deliberately. "Can this row be used?" is a judgement
with its own rules and its own tests; "turn this row into an object" is
mechanical. Keeping them apart means the reason a row was dropped is a value we
can assert on and log, not a silent `None` somewhere inside a mapper.

The repo rule this exists to enforce: **abstain over guess**. A row missing a
position is not a row at the equator, and a row missing a timestamp is not a row
from now. Those rows are skipped, and the reason is recorded.

The signature below is FROZEN so the tests (A4b/A4c) and the mapper (A3a) can be
written against it before the body exists. Do not change it without telling
Henry, Christopher and Silas.
"""

from __future__ import annotations

from typing import Any, Mapping

__all__ = ["unusable_reason", "REASONS"]

# The reasons a row is skipped. Kept as named constants so tests assert on a
# value rather than on prose, and so a log line can be counted per reason --
# "how many rows are we dropping and why" is the first question anyone asks of
# a live reader.
REASONS = {
    "MISSING_ENTITY": "no entity_id, so we cannot say which aircraft this is",
    "BAD_ENTITY": "entity_id is not in the expected 'icao24:<hex>' form",
    "MISSING_TIME": "no observed_at, so it cannot be placed in a window",
    "MISSING_POSITION": "no location, so there is nothing to compare",
    "BAD_POSITION": "latitude or longitude outside the valid range",
}


def unusable_reason(row: Mapping[str, Any]) -> str | None:
    """Return a key from ``REASONS`` if this row must be skipped, else ``None``.

    ``row`` is one record from the ``observations`` table as the reader selects
    it: the typed columns (``entity_id``, ``observed_at``, ``domain``,
    latitude/longitude pulled out of ``location``, ``sog``, ``cog``) plus the
    ``payload`` JSON as a dict.

    Only the fields an ``AdsbObservation`` *requires* can make a row unusable:
    icao24, observed_at, latitude, longitude. Everything else -- altitude,
    speed, NIC, NACp, callsign -- is legitimately absent all the time, and a
    missing optional field is data, not an error. Dropping those rows would
    quietly delete most of the feed.

    Returns the first reason found, so the caller gets one cause rather than a
    list it has to rank.
    """
    raise NotImplementedError(
        "A3b: Daniel — see docs/live_integration/TEAM_SPOOFING.md"
    )
