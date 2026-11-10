"""The live feed's payload is not the shape the CSV loader writes.

Two producers write ``observations.payload`` and they do not agree:

* ``scripts/load_observations_csv.py`` writes our own field names, flat.
* ``scripts/poll_adsb_feed.py`` stores the SENTINEL envelope verbatim, so the
  ADS-B fields are one level down under ``payload`` **and** under readsb's own
  names (``alt_baro``, ``nac_p``, ``flight``, ...).

The reader handled only the first. Measured against the live Xenith feed before
the fix: **0 of 2235 observations had any optional field populated** --
altitude, NIC, NACp, squawk, callsign, vertical rate, emitter category, all
``None``. Only ``sog`` and ``cog`` survived, because they are typed columns and
never go through ``payload`` at all.

Nothing raised. Every one of those fields is optional, so "not found" is
indistinguishable from "the aircraft did not report it", and a detector with no
altitude, no NIC and no callsign looks exactly like a quiet sky. That is what
makes this worth a file of its own: the failure is silent in both directions.

It is also not only ours. The reader is Spine A, shared with the other two
teams, and ``squawk`` carries the 7500/7600/7700 emergency codes the
no-fly-zone detector reads.

``LIVE_ENVELOPE`` below is a real row, copied from the table while the feed was
running.
"""

from __future__ import annotations

import pytest

from air.live.payload import observation_from_row

# A real envelope, taken verbatim from observations.payload on 2026-11-10.
# Trimmed only of fields no detector reads (rssi, messages, nav_modes, ...).
LIVE_ENVELOPE = {
    "key": "abea11",
    "source": "adsb",
    "payload": {
        "gs": 376.7,
        "hex": "abea11",
        "nic": 8,
        "nac_p": 9,
        "track": 257.0,
        "flight": "AAL2135 ",  # readsb pads to eight characters
        "squawk": "1320",
        "alt_baro": 34000,
        "alt_geom": 34850,
        "category": "A3",
        "baro_rate": 0,
    },
    "event_id": "university-adsb:abea11:1794326038900",
    "connector": "https.adsb_ingest",
    "observed_at": "2026-11-10T15:53:58.900Z",
    "producer_id": "university-adsb",
    "message_type": "aircraft_state",
    "published_at": "2026-11-10T15:53:59.732Z",
    "schema_version": "1",
}


def _row(payload, **overrides):
    row = {
        "entity_id": "icao24:abea11",
        "observed_at": "2026-11-10T15:53:58.900000+00:00",
        "latitude": 37.4,
        "longitude": -79.3,
        "sog": 376.7,
        "cog": 257.0,
        "payload": payload,
        "raw_record_ref": "university-adsb:abea11:1794326038900",
    }
    row.update(overrides)
    return row


def test_a_live_envelope_maps_every_field_a_detector_reads():
    """The regression this file exists for: all of these were None."""
    observation = observation_from_row(_row(LIVE_ENVELOPE))

    assert observation is not None
    assert observation.icao24 == "abea11"
    assert observation.altitude_ft == 34000
    assert observation.alt_geom_ft == 34850
    assert observation.vertical_rate_fpm == 0
    assert observation.nic == 8
    assert observation.nacp == 9
    assert observation.squawk == "1320"
    assert observation.callsign == "AAL2135"
    assert observation.emitter_category == "A3"


def test_the_padded_callsign_is_stripped():
    """readsb pads to eight characters; the CSV path strips.

    Left alone, "AAL2135 " and "AAL2135" are two different callsigns, and
    identity_drift_v1 compares callsigns for a living.
    """
    assert observation_from_row(_row(LIVE_ENVELOPE)).callsign == "AAL2135"


def test_a_blank_callsign_becomes_none_not_an_empty_string():
    """Absent must stay absent. "" is a value; None is "the feed did not say"."""
    envelope = {**LIVE_ENVELOPE, "payload": {**LIVE_ENVELOPE["payload"], "flight": "        "}}
    assert observation_from_row(_row(envelope)).callsign is None


def test_vertical_rate_falls_back_to_geometric():
    """Barometric preferred, geometric as fallback.

    The same order as air/normalizers/adsb_csv.py, so the two paths do not
    disagree about which rate they mean -- which the A4d parity test would
    catch, but only for rows the CSV also carries.
    """
    payload = {k: v for k, v in LIVE_ENVELOPE["payload"].items() if k != "baro_rate"}
    envelope = {**LIVE_ENVELOPE, "payload": {**payload, "geom_rate": -832}}
    assert observation_from_row(_row(envelope)).vertical_rate_fpm == -832


def test_barometric_wins_when_both_are_present():
    envelope = {
        **LIVE_ENVELOPE,
        "payload": {**LIVE_ENVELOPE["payload"], "baro_rate": 64, "geom_rate": -832},
    }
    assert observation_from_row(_row(envelope)).vertical_rate_fpm == 64


def test_on_ground_comes_from_the_altitude_field():
    """readsb has no boolean for it -- it sends "ground" where a number goes.

    Two things have to happen: on_ground becomes True, and the string must not
    reach altitude_ft, where the dataclass's own validation would reject it and
    cost us the whole observation rather than one field.
    """
    envelope = {**LIVE_ENVELOPE, "payload": {**LIVE_ENVELOPE["payload"], "alt_baro": "ground"}}
    observation = observation_from_row(_row(envelope))

    assert observation is not None, "a string altitude must not discard the row"
    assert observation.on_ground is True
    assert observation.altitude_ft is None


def test_airborne_rows_leave_on_ground_unstated():
    """None, not False. The feed is silent, and silence is not a denial."""
    assert observation_from_row(_row(LIVE_ENVELOPE)).on_ground is None


def test_the_flat_csv_payload_still_works():
    """The other producer. Both shapes have to keep working at once.

    The A4d parity test pins the CSV path field for field, so breaking this
    would fail there too -- but it would fail as a parity mismatch, which reads
    like a mapping bug rather than "the envelope change broke the other feed".
    """
    flat = {
        "altitude_ft": 34000,
        "alt_geom_ft": 34850,
        "vertical_rate_fpm": 0,
        "nic": 8,
        "nacp": 9,
        "squawk": "1320",
        "callsign": "AAL2135",
        "emitter_category": "A3",
        "on_ground": False,
        "receiver_id": "lynchburg",
    }
    observation = observation_from_row(_row(flat))

    assert observation.altitude_ft == 34000
    assert observation.nacp == 9
    assert observation.callsign == "AAL2135"
    assert observation.on_ground is False
    assert observation.receiver_id == "lynchburg"


def test_the_shape_is_detected_by_structure_not_by_a_flag():
    """A nested ``payload`` mapping means envelope; anything else means flat.

    No producer has to declare which it is, which matters because a third one
    would otherwise have to know to set a flag it has never heard of.
    """
    # A flat payload that happens to carry an unrelated "payload" key that is
    # not a mapping must still be read as flat.
    flat = {"altitude_ft": 1200, "payload": "not a mapping"}
    assert observation_from_row(_row(flat)).altitude_ft == 1200


def test_an_envelope_with_an_empty_inner_payload_costs_only_the_optional_fields():
    """Still a usable observation: position and time are typed columns."""
    envelope = {**LIVE_ENVELOPE, "payload": {}}
    observation = observation_from_row(_row(envelope))

    assert observation is not None
    assert observation.latitude == pytest.approx(37.4)
    assert observation.ground_speed_kt == pytest.approx(376.7)
    assert observation.altitude_ft is None


def test_squawk_survives_because_another_team_needs_it():
    """Not ours. 7500 hijack, 7600 radio failure, 7700 general emergency.

    Spoofing barely uses squawk; the no-fly-zone detector reads it for those
    codes. Losing it here would blind their detector, not ours, which is the
    kind of breakage that takes longest to notice.
    """
    envelope = {**LIVE_ENVELOPE, "payload": {**LIVE_ENVELOPE["payload"], "squawk": "7700"}}
    assert observation_from_row(_row(envelope)).squawk == "7700"
