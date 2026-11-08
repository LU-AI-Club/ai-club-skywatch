from __future__ import annotations

from datetime import datetime, timezone

from air.live.payload import observation_from_row


def test_observation_from_good_row_maps_columns_and_payload_fields():
    observed_at = datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc)
    row = {
        "entity_id": "icao24:a1b2c3",
        "observed_at": observed_at,
        "latitude": 37.5,
        "longitude": -79.2,
        "sog": 245.5,
        "cog": 182.0,
        "raw_record_ref": "lynchburg.csv:42",
        "payload": {
            "altitude_ft": 12000.0,
            "alt_geom_ft": 12150.0,
            "vertical_rate_fpm": 640.0,
            "nic": 8,
            "nacp": 9,
            "squawk": "1200",
            "callsign": "LIBERTY42",
            "emitter_category": "A3",
            "on_ground": False,
            "receiver_id": "lyh-01",
        },
    }

    observation = observation_from_row(row)

    assert observation is not None
    assert observation.icao24 == "a1b2c3"
    assert observation.observed_at == observed_at
    assert observation.latitude == 37.5
    assert observation.longitude == -79.2
    assert observation.ground_speed_kt == 245.5
    assert observation.track_deg == 182.0
    assert observation.source_row_id == "lynchburg.csv:42"
    assert observation.altitude_ft == 12000.0
    assert observation.alt_geom_ft == 12150.0
    assert observation.vertical_rate_fpm == 640.0
    assert observation.nic == 8
    assert observation.nacp == 9
    assert observation.squawk == "1200"
    assert observation.callsign == "LIBERTY42"
    assert observation.emitter_category == "A3"
    assert observation.on_ground is False
    assert observation.receiver_id == "lyh-01"


def test_missing_optional_fields_remain_none():
    row = {
        "entity_id": "icao24:a1b2c3",
        "observed_at": datetime(2026, 11, 3, 17, 0, tzinfo=timezone.utc),
        "latitude": 37.5,
        "longitude": -79.2,
        "payload": {},
    }

    observation = observation_from_row(row)

    assert observation is not None
    assert observation.altitude_ft is None
    assert observation.ground_speed_kt is None
    assert observation.track_deg is None
    assert observation.vertical_rate_fpm is None
    assert observation.nic is None
    assert observation.nacp is None
    assert observation.squawk is None
    assert observation.callsign is None
    assert observation.emitter_category is None
    assert observation.on_ground is None
    assert observation.receiver_id is None
    assert observation.source_row_id is None
