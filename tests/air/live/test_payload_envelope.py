"""Spine A on the live feed's row shape: the SENTINEL envelope.

scripts/poll_adsb_feed.py stores the envelope verbatim, so the readsb record
sits under payload["payload"] with readsb's names. Read flat only, every live
observation came back with altitude, NIC/NACp, squawk and callsign = None
(NFZ-12A / SPOOF-12C), and every detector still reported SUCCESS.

ENVELOPE below is a real row from the poller (Lynchburg antenna, 2026-11-10).
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
from typing import Any

from air.live.payload import observation_from_row

ENVELOPE: dict[str, Any] = {
    "key": "a49f89",
    "source": "adsb",
    "payload": {
        "gs": 502.3, "rc": 186, "gva": 2, "hex": "a49f89", "lat": 37.866577,
        "lon": -79.743795, "nic": 8, "sda": 2, "sil": 3, "mlat": [], "rssi": -24.4,
        "seen": 0.1, "tisb": [], "modea": True, "modec": True, "nac_p": 9, "nac_v": 1,
        "track": 85.9, "flight": "UAL2364 ", "squawk": "1574", "nav_qnh": 1013.6,
        "version": 2, "alt_baro": 39000, "alt_geom": 39850, "category": "A3",
        "messages": 644, "nic_baro": 1, "seen_pos": 0.1, "sil_type": "perhour",
        "baro_rate": 0, "emergency": "none", "nav_heading": 92.1,
        "nav_altitude_mcp": 39008,
    },
    "event_id": "university-adsb:a49f89:1794340017700",
    "connector": "https.adsb_ingest",
    "observed_at": "2026-11-10T19:46:57.700Z",
    "producer_id": "university-adsb",
    "message_type": "aircraft_state",
    "published_at": "2026-11-10T19:46:58.608Z",
    "schema_version": "1",
}


def _row(payload: dict[str, Any]) -> dict[str, Any]:
    """The row read_window would select for that poller insert."""
    return {
        "entity_id": "icao24:a49f89",
        "observed_at": datetime(2026, 11, 10, 19, 46, 57, 700000, tzinfo=UTC),
        "domain": "air",
        "latitude": 37.866577,
        "longitude": -79.743795,
        "sog": 502.3,
        "cog": 85.9,
        "raw_record_ref": "university-adsb:a49f89:1794340017700",
        "payload": payload,
    }


def test_live_envelope_row_keeps_altitude_and_integrity_fields() -> None:
    obs = observation_from_row(_row(ENVELOPE))
    assert obs is not None
    assert (obs.altitude_ft, obs.alt_geom_ft, obs.vertical_rate_fpm) == (39000, 39850, 0)
    assert (obs.nic, obs.nacp) == (8, 9)
    assert obs.squawk == "1574"
    assert obs.callsign == "UAL2364"  # readsb pads the callsign; stripped
    assert obs.emitter_category == "A3"
    assert obs.on_ground is False


def test_surface_aircraft_reports_ground_not_an_altitude() -> None:
    envelope = copy.deepcopy(ENVELOPE)
    envelope["payload"]["alt_baro"] = "ground"
    del envelope["payload"]["alt_geom"]
    obs = observation_from_row(_row(envelope))
    assert obs is not None
    assert obs.altitude_ft is None and obs.alt_geom_ft is None
    assert obs.on_ground is True


def test_flat_keys_still_win_over_the_nested_record() -> None:
    # CSV-loaded rows are flat; a row carrying both keeps the flat value.
    envelope = copy.deepcopy(ENVELOPE)
    envelope["altitude_ft"] = 12000.0
    envelope["callsign"] = "LIBERTY42"
    obs = observation_from_row(_row(envelope))
    assert obs is not None
    assert obs.altitude_ft == 12000.0 and obs.callsign == "LIBERTY42"
    assert obs.nacp == 9  # still filled from the nested record


def test_missing_nested_fields_stay_none_and_blank_callsign_is_none() -> None:
    envelope = copy.deepcopy(ENVELOPE)
    for key in ("alt_baro", "alt_geom", "baro_rate", "nic", "nac_p", "squawk", "category"):
        del envelope["payload"][key]
    envelope["payload"]["flight"] = "        "
    obs = observation_from_row(_row(envelope))
    assert obs is not None
    assert obs.altitude_ft is None and obs.nic is None and obs.squawk is None
    assert obs.callsign is None and obs.on_ground is None


def test_geometric_rate_is_used_when_there_is_no_baro_rate() -> None:
    envelope = copy.deepcopy(ENVELOPE)
    del envelope["payload"]["baro_rate"]
    envelope["payload"]["geom_rate"] = -640
    obs = observation_from_row(_row(envelope))
    assert obs is not None and obs.vertical_rate_fpm == -640
