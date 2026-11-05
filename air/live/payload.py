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

from datetime import datetime
from typing import Any, Mapping

from air.models.observation import AdsbObservation

__all__ = ["observation_from_row"]


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _opt_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


def _opt_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = _opt_str(value)
    if text is None:
        return None
    lowered = text.lower()
    if lowered in {"true", "1"}:
        return True
    if lowered in {"false", "0"}:
        return False
    return None


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
    payload = row.get("payload")
    if not isinstance(payload, Mapping):
        payload = {}

    entity_id = _opt_str(row.get("entity_id"))
    if entity_id is None:
        return None

    prefix = "icao24:"
    if not entity_id.lower().startswith(prefix):
        return None
    icao24 = _opt_str(entity_id[len(prefix):])
    if icao24 is None:
        return None

    observed_at = row.get("observed_at")
    if observed_at is None or not isinstance(observed_at, datetime | str):
        return None

    latitude = _opt_float(row.get("latitude"))
    longitude = _opt_float(row.get("longitude"))
    if latitude is None or longitude is None:
        return None

    try:
        return AdsbObservation(
            icao24=icao24,
            observed_at=observed_at,
            latitude=latitude,
            longitude=longitude,
            altitude_ft=_opt_float(payload.get("altitude_ft")),
            ground_speed_kt=_opt_float(row.get("sog")),
            track_deg=_opt_float(row.get("cog")),
            vertical_rate_fpm=_opt_float(payload.get("vertical_rate_fpm")),
            nic=_opt_int(payload.get("nic")),
            nacp=_opt_int(payload.get("nacp")),
            squawk=_opt_str(payload.get("squawk")),
            callsign=_opt_str(payload.get("callsign")),
            receiver_id=_opt_str(payload.get("receiver_id")),
            alt_geom_ft=_opt_float(payload.get("alt_geom_ft")),
            on_ground=_opt_bool(payload.get("on_ground")),
            emitter_category=_opt_str(payload.get("emitter_category")),
            source_row_id=_opt_str(row.get("raw_record_ref")),
        )
    except (TypeError, ValueError):
        return None
