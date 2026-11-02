"""Stream A - ADS-B state loader for the no-fly-zone detector.

Reads aircraft observations into :class:`AircraftState`, choosing the format by
file extension:

``.csv``
    A readsb/tar1090 field dump, the format of ``data/lynchburg_adsb.csv``.
    Columns used: ``h`` icao24, ``timestamp``, ``la``/``lo``, ``ab`` baro and
    ``ag`` geometric altitude (feet), ``gs`` knots, ``tr`` track, ``f``
    callsign, ``sq`` squawk, ``c`` emitter category, ``n`` NIC, ``np`` NACp,
    ``og`` on-ground flag. Every other column is ignored. Streamed row by row,
    so a large file is never held in memory. The shared
    ``air.normalizers.adsb_csv`` reads the same file but drops ``ag``, ``og``
    and ``c``, which this detector needs (geometric altitude for MSL bands,
    the on-ground filter), so this detector keeps its own mapping;
    ``COLUMN_MAP.md`` in this folder documents each column.
anything else
    A JSON array using AircraftState field names. Unknown keys are ignored.

Inputs
------
path:
    The file to read. Opened on first iteration, not when called.

Outputs
-------
An iterator of :class:`AircraftState` in file order.

Failure causes
--------------
FileNotFoundError
    ``path`` does not exist.
ValueError
    The JSON is malformed or the top-level value is not an array; or a CSV has
    no header row or lacks a required column (``h``, ``timestamp``, ``la``,
    ``lo``).

Rows with no ID or timestamp are silently skipped. Other unusable rows are
skipped with a warning naming the file and row number (the first
``_MAX_ROW_WARNINGS``, then one summary line, so a large file cannot flood the
log). At least one altitude is required; supplied altitudes must be finite
numbers. Optional fields default to None, on_ground to False, and
source_row_id to the file path and row number (data rows counted from 1).
Naive ISO timestamps are assumed UTC; aware timestamps are converted to UTC.

Notes
-----
Parquet (the collector's output) is not supported yet.
No I/O at import time: the file is opened only when the returned iterator is
first consumed.
"""
from __future__ import annotations

import csv
import json
import logging
import math
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from air.detectors.no_fly_zone.types import AircraftState

logger = logging.getLogger(__name__)

# How many per-row skip warnings to log before switching to a summary line.
# Logging volume, not detector behaviour, so it is not a config value.
_MAX_ROW_WARNINGS = 20

# readsb/tar1090 CSV column -> AircraftState field (see the module docstring).
_CSV_COLUMNS: dict[str, str] = {
    "h": "icao24",
    "timestamp": "timestamp",
    "la": "lat",
    "lo": "lon",
    "ab": "alt_baro_ft",
    "ag": "alt_geom_ft",
    "gs": "ground_speed_kt",
    "tr": "track_deg",
    "f": "callsign",
    "sq": "squawk",
    "c": "emitter_category",
    "n": "nic",
    "np": "nac_p",
    "og": "on_ground",
}
_CSV_REQUIRED = ("h", "timestamp", "la", "lo")
_CSV_TRUE = frozenset({"true", "1"})
_CSV_FALSE = frozenset({"false", "0"})


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
    rows = _csv_rows(path) if path.suffix.lower() == ".csv" else _json_rows(path)
    skipped = 0
    for row_number, row in enumerate(rows, start=1):
        try:
            state = _state_from_row(row, f"{path}:{row_number}")
        except ValueError as exc:
            skipped += 1
            if skipped <= _MAX_ROW_WARNINGS:
                logger.warning("Skipping %s row %d: %s", path, row_number, exc)
            continue
        if state is not None:
            yield state
    if skipped > _MAX_ROW_WARNINGS:
        logger.warning(
            "Skipped %d unusable rows in %s (first %d listed above)",
            skipped, path, _MAX_ROW_WARNINGS,
        )


def _json_rows(path: Path) -> Iterable[Any]:
    with path.open(encoding="utf-8") as source:
        rows = json.load(source)
    if not isinstance(rows, list):
        raise ValueError("ADS-B JSON must contain an array of rows")
    return rows


def _csv_rows(path: Path) -> Iterator[dict[str, Any]]:
    """Stream a readsb CSV as dicts keyed by AircraftState field names.

    Blank cells become None. ``og`` becomes a bool when it reads true/false;
    anything else is passed through so the row builder rejects it.
    """
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        missing = [c for c in _CSV_REQUIRED if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"ADS-B CSV {path} is missing required columns: {missing}")
        for raw in reader:
            row: dict[str, Any] = {}
            for column, field_name in _CSV_COLUMNS.items():
                value = (raw.get(column) or "").strip()
                row[field_name] = value or None
            flag = row["on_ground"]
            if flag is None:
                row["on_ground"] = False
            elif flag.lower() in _CSV_TRUE:
                row["on_ground"] = True
            elif flag.lower() in _CSV_FALSE:
                row["on_ground"] = False
            yield row


def _state_from_row(row: Any, default_row_id: str) -> AircraftState | None:
    """Build one state, ``None`` to skip silently, or raise ValueError."""
    if not isinstance(row, dict):
        raise ValueError("row must be an object")
    icao24 = _text(row, "icao24")
    raw_timestamp = _text(row, "timestamp")
    if not icao24 or not raw_timestamp:
        return None
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

    return AircraftState(
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
        source_row_id=_text(row, "source_row_id") or default_row_id,
    )
