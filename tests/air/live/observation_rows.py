"""Sample ``observations`` rows for the live-reader tests.

Shaped like rows read back from the real table, as written by
scripts/load_observations_csv.py (observation_to_row + INSERT_SQL):

* typed columns: observed_at, entity_id, domain, source_id, sog, cog,
  heading, nav_status, h3_index_res7/res9, provenance_id, raw_record_ref
* ``payload`` JSONB, which psycopg returns as a dict. Altitude, NIC, NACp,
  squawk, callsign etc. live ONLY here, there is no typed column for them.
* ``latitude`` / ``longitude``: the table stores a PostGIS ``location``;
  the reader's SELECT is assumed to expose it as these two floats.

Cases:
  GOOD_ROW               everything filled in
  PAYLOAD_ONLY_ROW       altitude/NIC only inside payload (typed sog/cog empty)
  BROKEN_ROWS            must be skipped (MISSING_POSITION / MISSING_TIME / MISSING_ENTITY)
  EMPTY_ROWS             an empty result set
"""

from __future__ import annotations

from datetime import datetime, timezone

_T0 = datetime(2026, 11, 3, 14, 5, 9, tzinfo=timezone.utc)

def _payload(**overrides) -> dict:
    """Full payload with the exact keys the loader writes."""
    base = {
        "hex": "a1b2c3",
        "altitude_ft": 3500,
        "alt_geom_ft": 3650,
        "ground_speed_kt": 120.5,
        "track_deg": 275.0,
        "vertical_rate_fpm": 64,
        "nic": 8,
        "nacp": 9,
        "squawk": "1200",
        "callsign": "N123AB",
        "emitter_category": "A1",
        "on_ground": False,
        "receiver_id": "lynchburg",
    }
    base.update(overrides)
    return base

def make_row(**overrides) -> dict:
    """A valid observations row; override any column to build variants."""
    row = {
        "observed_at": _T0,
        "entity_id": "icao24:a1b2c3",
        "domain": "air",
        "source_id": "adsb",
        "latitude": 37.3267,
        "longitude": -79.2000,
        "h3_index_res7": 608734220323389439,  # h3 res 7 for (37.3267, -79.2000)
        "h3_index_res9": 617741419574460415,  # h3 res 9 for (37.3267, -79.2000)
        "sog": 120.5,
        "cog": 275.0,
        "heading": None,  # readsb true-heading is empty in this export
        "nav_status": None,
        "payload": _payload(),
        "provenance_id": "11111111-1111-4111-8111-111111111111",
        "raw_record_ref": "data/lynchburg_adsb.csv:101",
    }
    row.update(overrides)
    return row

# 1. Good row: every column filled, full payload.
GOOD_ROW = make_row()

# 2. Payload-only fields: altitude and NIC exist ONLY in payload. The typed
#    sog/cog are empty, so a reader that drops the payload loses them.
PAYLOAD_ONLY_ROW = make_row(
    observed_at=datetime(2026, 11, 3, 14, 5, 11, tzinfo=timezone.utc),
    entity_id="icao24:d4e5f6",
    sog=None,
    cog=None,
    payload=_payload(
        hex="d4e5f6",
        altitude_ft=34000,
        alt_geom_ft=34250,
        nic=7,
        nacp=10,
        callsign="DAL456",
    ),
    raw_record_ref="data/lynchburg_adsb.csv:102",
)
PAYLOAD_ONLY_EXPECTED = {"altitude_ft": 34000, "nic": 7, "nacp": 10}

# 3. Broken rows: each must be skipped, one per named reason.
BROKEN_NO_POSITION = make_row(  # MISSING_POSITION
    entity_id="icao24:0a0b0c",
    latitude=None,
    longitude=None,
    payload=_payload(hex="0a0b0c", altitude_ft=5000),
    raw_record_ref="data/lynchburg_adsb.csv:103",
)
BROKEN_NO_TIME = make_row(  # MISSING_TIME
    entity_id="icao24:0d0e0f",
    observed_at=None,
    payload=_payload(hex="0d0e0f"),
    raw_record_ref="data/lynchburg_adsb.csv:104",
)
BROKEN_NO_ENTITY = make_row(  # MISSING_ENTITY
    entity_id=None,
    payload=_payload(hex=None),
    raw_record_ref="data/lynchburg_adsb.csv:105",
)
BROKEN_ROWS = [BROKEN_NO_POSITION, BROKEN_NO_TIME, BROKEN_NO_ENTITY]

# 4. Empty set.
EMPTY_ROWS: list[dict] = []

# Convenience bundles.
VALID_ROWS = [GOOD_ROW, PAYLOAD_ONLY_ROW]
MIXED_ROWS = [GOOD_ROW, BROKEN_NO_POSITION, PAYLOAD_ONLY_ROW, BROKEN_NO_TIME, BROKEN_NO_ENTITY]