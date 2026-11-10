"""Turn one `observations` row into one AdsbObservation.

OWNER: Henry (ticket A3a) — see docs/live_integration/TEAM_SPOOFING.md.

``read_window`` owns the SQL; this owns the shape. Separating them means the
mapping can be tested on a plain dict with no database at all, which is the
difference between a test that runs in CI and one that needs Docker.

This is the piece the whole club depends on being right. Proximity and
No-Fly-Zone read the same table through ``read_window``, so a field pulled out
of ``payload`` incorrectly here is wrong for all three detectors at once.

**Where the fields live.** The `observations` table keeps only the cross-domain
columns typed -- a maritime vessel and an aircraft share time, position, speed
and course, so those are columns. Everything specific to ADS-B is inside the
``payload`` JSON:

    column            -> AdsbObservation
    ---------------------------------------
    entity_id         -> icao24          ('icao24:a1b2c3' -> 'a1b2c3')
    observed_at       -> observed_at
    location          -> latitude, longitude
    sog               -> ground_speed_kt
    cog               -> track_deg
    raw_record_ref    -> source_row_id

    payload key       -> AdsbObservation
    ---------------------------------------
    altitude_ft       -> altitude_ft
    alt_geom_ft       -> alt_geom_ft
    vertical_rate_fpm -> vertical_rate_fpm
    nic               -> nic
    nacp              -> nacp
    squawk            -> squawk
    callsign          -> callsign
    emitter_category  -> emitter_category
    on_ground         -> on_ground
    receiver_id       -> receiver_id

**The live feed stores a different shape.** ``scripts/poll_adsb_feed.py`` keeps
the SENTINEL envelope verbatim, and the receiver's own readsb record sits one
level down, under ``payload["payload"]``, with readsb's names. Read flat only,
every live row came back with altitude, NIC/NACp, squawk and callsign all None
-- and every detector still reported SUCCESS. So a field missing from the flat
keys is looked up in the nested record:

    payload["payload"] key -> AdsbObservation
    ---------------------------------------
    alt_baro          -> altitude_ft      ("ground" -> None, on_ground True)
    alt_geom          -> alt_geom_ft
    baro_rate         -> vertical_rate_fpm (geom_rate if no baro_rate)
    nic               -> nic
    nac_p             -> nacp
    squawk            -> squawk
    flight            -> callsign         (readsb pads it with spaces)
    category          -> emitter_category

Flat keys always win, so CSV-loaded rows map exactly as before.

The target of that mapping is not a guess: ``air/normalizers/adsb_csv.py``
already produces ``AdsbObservation``s from the raw CSV, and
``scripts/load_observations_csv.py`` already writes those same observations
into this table. Read both -- between them they define exactly what a row
contains and what it has to turn back into. Noah's parity test (A4d) asserts
the round trip.

The signature below is FROZEN so the tests (A4b/A4c) can be written against it
before the body exists. Do not change it without telling Christopher, Silas and
Noah.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from air.live.row_validation import unusable_reason
from air.models.observation import AdsbObservation

__all__ = ["observation_from_row"]

_log = logging.getLogger(__name__)

# The ADS-B fields that live inside ``payload`` rather than in typed columns.
# Each name is the same on both sides: the loader writes
# ``payload["altitude_ft"] = obs.altitude_ft``, so we read it straight back.
_PAYLOAD_FIELDS = (
    "altitude_ft",
    "alt_geom_ft",
    "vertical_rate_fpm",
    "nic",
    "nacp",
    "squawk",
    "callsign",
    "emitter_category",
    "on_ground",
    "receiver_id",
)

# The live envelope: readsb names under payload["payload"] (see module docstring).
_NESTED_KEY = "payload"
_ENVELOPE_FIELDS = {
    "altitude_ft": "alt_baro",
    "alt_geom_ft": "alt_geom",
    "vertical_rate_fpm": "baro_rate",
    "nic": "nic",
    "nacp": "nac_p",
    "squawk": "squawk",
    "callsign": "flight",
    "emitter_category": "category",
}
_GROUND = "ground"

_ENTITY_PREFIX = "icao24:"


def _payload_dict(raw: Any) -> Mapping[str, Any]:
    """The payload as a dict. Absent or unreadable means "no optional fields".

    psycopg hands JSONB back as a dict already; a JSON string is accepted too so
    a fixture or a different driver does not break the mapping. Nothing required
    lives in ``payload``, so a bad payload costs the optional fields only --
    they stay ``None`` rather than being guessed.
    """
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, Mapping) else {}
    return {}


def _optional_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """The optional ADS-B fields: flat keys first, then the live envelope's record."""
    fields = {name: payload.get(name) for name in _PAYLOAD_FIELDS}
    nested = payload.get(_NESTED_KEY)
    if not isinstance(nested, Mapping):
        return fields  # a CSV-loaded row: flat only, unchanged
    for name, key in _ENVELOPE_FIELDS.items():
        if fields[name] is None:
            fields[name] = nested.get(key)
    if fields["vertical_rate_fpm"] is None:
        fields["vertical_rate_fpm"] = nested.get("geom_rate")
    # readsb reports a surface aircraft as alt_baro "ground", not a number.
    alt_baro = nested.get("alt_baro")
    if fields["on_ground"] is None and alt_baro is not None:
        fields["on_ground"] = alt_baro == _GROUND
    if fields["altitude_ft"] == _GROUND:
        fields["altitude_ft"] = None
    if isinstance(fields["callsign"], str):
        fields["callsign"] = fields["callsign"].strip() or None
    return fields


def observation_from_row(row: Mapping[str, Any]) -> AdsbObservation | None:
    """Map one ``observations`` row to an ``AdsbObservation``, or ``None``.

    ``row`` is one record as the reader selects it: the typed columns
    (``entity_id``, ``observed_at``, ``domain``, latitude/longitude taken out
    of ``location``, ``sog``, ``cog``, ``raw_record_ref``) plus ``payload`` as
    a dict.

    Returns ``None`` when ``row_validation.unusable_reason`` gives a reason --
    a row we cannot form an observation from is skipped, never guessed at. An
    absent *optional* field is not a reason: it stays ``None`` on the
    observation, which is normal and is information the detector uses.

    Must not raise on a malformed row. The live reader sees whatever the feed
    produced, and one bad record cannot be allowed to kill a window.
    """
    try:
        if unusable_reason(row) is not None:
            return None

        payload = _payload_dict(row.get("payload"))
        return AdsbObservation(
            icao24=str(row["entity_id"]).removeprefix(_ENTITY_PREFIX),
            observed_at=row["observed_at"],
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            ground_speed_kt=row.get("sog"),
            track_deg=row.get("cog"),
            source_row_id=row.get("raw_record_ref"),
            **_optional_fields(payload),
        )
    except Exception:  # noqa: BLE001 -- one bad row must not kill a window
        _log.debug("skipping observations row that could not be mapped", exc_info=True)
        return None
