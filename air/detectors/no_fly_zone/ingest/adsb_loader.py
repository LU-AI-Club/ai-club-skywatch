"""Stream A - ADS-B state loader.

Reads a JSON array using AircraftState field names. Unknown keys are ignored.
CSV and Parquet are not supported yet.

Inputs
------
path:
    JSON file to read into memory on first iteration.

Outputs
-------
An iterator of :class:`AircraftState` in file order. The raw JSON document
is held in memory; aircraft records are constructed one at a time.

Failure causes
--------------
FileNotFoundError
    ``path`` does not exist.
ValueError
    The JSON is malformed or the top-level value is not an array.

Missing IDs or timestamps are silently skipped. Other unusable rows are skipped
with a warning identifying the file and row number. At least one altitude is
required; supplied altitudes must be finite numbers. Optional fields default to
None, on_ground to False, and source_row_id to the file path and row number.
Naive ISO timestamps are assumed UTC; aware timestamps are converted to UTC.

Notes
-----
No I/O at import time: the file is opened only when the returned iterator is
first consumed.
"""
from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..types import AircraftState

logger = logging.getLogger(__name__)


def _number(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError(f"{key} must be a finite number")
    try:
        number = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{key} must be a finite number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{key} must be a finite number")
    return number


def _integer(row: dict[str, Any], key: str) -> int | None:
    number = _number(row, key)
    if number is None:
        return None
    if not number.is_integer():
        raise ValueError(f"{key} must be an integer")
    return int(number)


def _text(row: dict[str, Any], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip() or None


def load_states(path: str | Path) -> Iterator[AircraftState]:
    """Yield one :class:`AircraftState` per usable row of ``path``."""
    path = Path(path)
    with path.open(encoding="utf-8") as source:
        rows = json.load(source)
    if not isinstance(rows, list):
        raise ValueError("ADS-B JSON must contain an array of rows")

    for row_number, row in enumerate(rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("row must be an object")
            icao24 = _text(row, "icao24")
            raw_timestamp = _text(row, "timestamp")
            if not icao24 or not raw_timestamp:
                continue
            try:
                timestamp = datetime.fromisoformat(raw_timestamp)
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=UTC)
                timestamp = timestamp.astimezone(UTC)
            except (ValueError, OverflowError) as exc:
                raise ValueError("timestamp is not a valid ISO datetime") from exc

            lat, lon = _number(row, "lat"), _number(row, "lon")
            if lat is None or not -90 <= lat <= 90:
                raise ValueError("lat is missing or outside [-90, 90]")
            if lon is None or not -180 <= lon <= 180:
                raise ValueError("lon is missing or outside [-180, 180]")
            alt_baro = _number(row, "alt_baro_ft")
            alt_geom = _number(row, "alt_geom_ft")
            if alt_baro is None and alt_geom is None:
                raise ValueError("altitude is missing")
            on_ground = row.get("on_ground", False)
            if not isinstance(on_ground, bool):
                raise ValueError("on_ground must be a boolean")

            state = AircraftState(
                icao24=icao24,
                timestamp=timestamp,
                lat=lat,
                lon=lon,
                alt_baro_ft=alt_baro,
                alt_geom_ft=alt_geom,
                ground_speed_kt=_number(row, "ground_speed_kt"),
                track_deg=_number(row, "track_deg"),
                callsign=_text(row, "callsign"),
                squawk=_text(row, "squawk"),
                emitter_category=_text(row, "emitter_category"),
                nic=_integer(row, "nic"),
                nac_p=_integer(row, "nac_p"),
                on_ground=on_ground,
                source_row_id=_text(row, "source_row_id") or f"{path}:{row_number}",
            )
        except ValueError as exc:
            logger.warning("Skipping %s row %d: %s", path, row_number, exc)
            continue
        yield state
