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
import math
from typing import Any, Mapping

_ENTITY_PREFIX = "icao24:"
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

__all__ = ["unusable_reason", "REASONS"]

# The reasons a row is skipped. Kept as named constants so tests assert on a
# value rather than on prose, and so a log line can be counted per reason --
# "how many rows are we dropping and why" is the first question anyone asks of
# a live reader.
REASONS = {
    "MISSING_ENTITY": "no entity_id, so we cannot say which aircraft this is",
    "BAD_ENTITY": "entity_id is not in the expected 'icao24:<hex>' form",
    "NON_ICAO_ADDRESS": "address is not a real ICAO 24-bit address (TIS-B, ADS-R or anonymised)",
    "MISSING_TIME": "no observed_at, so it cannot be placed in a window",
    "MISSING_POSITION": "no location, so there is nothing to compare",
    "BAD_POSITION": "latitude or longitude outside the valid range",
}

def _absent(value: Any) -> bool:
    """None, blank string, or NaN: there is no value here.

    0 and 0.0 are NOT absent. Zero is a real coordinate.
    """
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def unusable_reason(row: Mapping[str, Any]) -> str | None:
    # 1. Which aircraft is this?
    entity_id = row.get("entity_id")
    if _absent(entity_id):
        return "MISSING_ENTITY"
    if not isinstance(entity_id, str) or not entity_id.startswith(_ENTITY_PREFIX):
        return "BAD_ENTITY"
    hex_part = entity_id[len(_ENTITY_PREFIX):]
    if not hex_part:
        return "BAD_ENTITY"
    # readsb and tar1090 prefix a non-ICAO address with "~": TIS-B relays,
    # ADS-R rebroadcasts and anonymised targets. Separated from BAD_ENTITY
    # because it is not malformed input -- the feed is telling us plainly that
    # this address is not an airframe's. It gets its own reason so the live
    # counters distinguish "the feed sent us something we cannot parse" from
    # "the feed sent us a target we deliberately do not track".
    #
    # We skip them: a "~" address is assigned by the ground station and is
    # reused, so two aircraft can share one. Keying our pairwise physics rules
    # on it would make consecutive reports hop between airframes and read as
    # impossible jumps -- our own false positives. air/normalizers/adsb_csv.py
    # drops the same addresses, and the A4d parity test holds the two paths to
    # each other.
    if hex_part.startswith("~"):
        return "NON_ICAO_ADDRESS"
    if len(hex_part) != 6 or not all(c in _HEX_DIGITS for c in hex_part):
        return "BAD_ENTITY"

    # 2. When was it seen?
    if _absent(row.get("observed_at")):
        return "MISSING_TIME"

    # 3. Where was it? Abstain over guess: no position is not (0, 0).
    lat = row.get("latitude")
    lon = row.get("longitude")
    if _absent(lat) or _absent(lon):
        return "MISSING_POSITION"

    # 4. Is the position real?
    for value in (lat, lon):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return "BAD_POSITION"
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return "BAD_POSITION"  # also catches +/- infinity

    return None