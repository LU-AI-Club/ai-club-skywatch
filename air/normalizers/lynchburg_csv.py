"""Read raw Lynchburg ADS-B rows into ``AdsbObservation`` records.

The raw CSV carries 53 terse columns; every detector consumes the shared
``AdsbObservation`` contract. This module is the bridge, and it is the only
place where column names and units are interpreted.

Usage::

    from air.normalizers.lynchburg_csv import load_csv

    observations = load_csv("data/lynchburg_adsb.csv")
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from air.models.observation import AdsbObservation

# Message source types we trust. Everything else reached us second-hand:
#   adsr_icao  - rebroadcast on another link by a ground station
#   tisb_other - assembled by a ground station, often from radar
# Their timing and position semantics differ from a direct reception, so they
# would trip the kinematic gates without anything being wrong.
_DIRECT_SOURCES: frozenset[str] = frozenset({"adsb_icao"})

# Radius of containment (metres) -> NIC, from the ADS-B standard (DO-260B).
# Bounds are the values this feed reports, so 186 and 371 stand in for the
# spec's 185.2 m (0.1 NM) and 370.4 m (0.2 NM).
_NIC_BY_MAX_RC: tuple[tuple[float, int], ...] = (
    (7.5, 11),
    (25.0, 10),
    (75.0, 9),
    (186.0, 8),
    (371.0, 7),
    (1112.0, 6),
    (1852.0, 5),
    (3704.0, 4),
    (7408.0, 3),
    (14816.0, 2),
    (37040.0, 1),
)


def rc_to_nic(rc_m: float | None) -> int | None:
    """Convert a radius of containment in metres to a NIC value.

    NIC says how much an aircraft trusts its own position: 11 is a tight fix,
    0 means it has no idea.

    Returns ``None`` when the radius is unknown -- missing, or 0, which is how
    this feed spells "unknown". Callers must abstain on ``None`` rather than
    read it as "integrity is zero", which would be a detection.
    """
    if rc_m is None:
        return None

    rc = float(rc_m)
    if rc <= 0.0:
        return None

    for max_rc, nic in _NIC_BY_MAX_RC:
        if rc <= max_rc:
            return nic

    return 0


def is_direct_adsb(row: Mapping[str, Any]) -> bool:
    """True if we received this message straight from the aircraft.

    Column ``t`` carries the source type. Only ``adsb_icao`` is a direct
    reception; the rest are relayed or ground-derived and are dropped before
    any physics check sees them.
    """
    source = row.get("t")
    if not isinstance(source, str):
        return False
    return source.strip().lower() in _DIRECT_SOURCES


def _as_float(value: Any) -> float | None:
    """Parse a CSV cell as a float, treating blanks as missing.

    A blank cell means "not reported", which is ``None`` -- never 0. Zero is a
    real altitude and a real vertical rate, so conflating the two would invent
    data the aircraft never sent.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _as_int(value: Any) -> int | None:
    """Parse a CSV cell as an int, treating blanks as missing."""
    number = _as_float(value)
    return None if number is None else int(number)


def _as_text(value: Any) -> str | None:
    """Parse a CSV cell as text, treating blanks as missing."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse the feed's timestamp into a timezone-aware UTC datetime.

    The column holds ISO-8601 text, sometimes ending in ``Z`` and sometimes
    carrying an explicit offset. Anything unparseable is missing, not an
    error -- one malformed row must not stop a 284,000-row file.
    """
    text = _as_text(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def row_to_observation(row: Mapping[str, Any]) -> AdsbObservation | None:
    """Convert one raw CSV row into an ``AdsbObservation``.

    Returns ``None`` when the row cannot be used: a relayed message, or one
    missing the aircraft id, timestamp or position. Those three are the
    minimum a detector needs; everything else may legitimately be absent.

    Altitude comes from ``ag`` (geometric/GPS), never ``ab`` (barometric).
    The two differ by hundreds to thousands of feet depending on pressure,
    and mixing them would invent climbs and descents that never happened.
    """
    if not is_direct_adsb(row):
        return None

    icao24 = _as_text(row.get("h"))
    if icao24 is None:
        return None

    observed_at = _parse_timestamp(row.get("timestamp"))
    if observed_at is None:
        return None

    latitude = _as_float(row.get("la"))
    longitude = _as_float(row.get("lo"))
    if latitude is None or longitude is None:
        return None

    try:
        return AdsbObservation(
            icao24=icao24,
            observed_at=observed_at,
            latitude=latitude,
            longitude=longitude,
            altitude_ft=_as_float(row.get("ag")),
            ground_speed_kt=_as_float(row.get("gs")),
            track_deg=_as_float(row.get("tr")),
            vertical_rate_fpm=_as_float(row.get("br")),
            nic=rc_to_nic(_as_float(row.get("rc"))),
            nacp=_as_int(row.get("np")),
            squawk=_as_text(row.get("sq")),
            callsign=_as_text(row.get("f")),
            # receiver_id stays None: this feed carries no receiver column.
            # The club's own antenna will, and that is where it comes from.
        )
    except ValueError:
        # Out-of-range latitude or longitude. The contract rejects it, and a
        # corrupt row is not worth stopping the load for.
        return None


def iter_observations(path: str | Path) -> Iterator[AdsbObservation]:
    """Stream observations from a CSV, one row at a time.

    The real file is 70 MB, so rows are read lazily rather than held in
    memory all at once. ``load_csv`` wraps this when a list is wanted.
    """
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            observation = row_to_observation(row)
            if observation is not None:
                yield observation


def load_csv(path: str | Path) -> list[AdsbObservation]:
    """Read a whole CSV into a list of observations.

    Unusable rows -- relayed messages and rows missing id, time or position --
    are skipped silently. On ``data/lynchburg_adsb.csv`` this keeps 284,337 of
    284,476 rows; the 139 dropped are relayed, not broken.
    """
    return list(iter_observations(path))


__all__ = [
    "rc_to_nic",
    "is_direct_adsb",
    "row_to_observation",
    "iter_observations",
    "load_csv",
]
