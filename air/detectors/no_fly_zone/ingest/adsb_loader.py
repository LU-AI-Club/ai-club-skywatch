"""Stream A - ADS-B state loader.

Reads recorded ADS-B rows (CSV, or the hourly Parquet written by ``collect/``)
and yields validated :class:`AircraftState` records.

Inputs
------
path:
    File to read. CSV uses the abbreviated ADS-B Exchange-style columns
    documented in CLAUDE.md (``h``, ``la``, ``lo``, ``ab``, ``ag``, ``f``,
    ``c``, ``sq``, ``gs``, ``tr``, ``nb``, ``np``, ``nv``, ``og``,
    ``timestamp``). That mapping is provisional; this stream confirms it.

Outputs
-------
An iterator of :class:`AircraftState` in file order. Streaming rather than a
list so an hour of 1 Hz data never has to sit in memory at once.

Failure causes
--------------
FileNotFoundError
    ``path`` does not exist.
ValueError
    A required column is missing, or ``timestamp`` will not parse as UTC.

Rows that are individually unusable (no position, unparseable altitude) are
skipped rather than raising, so one bad row cannot kill an hour of data.

Notes
-----
No I/O at import time: the file is opened only when the returned iterator is
first consumed.
"""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..types import AircraftState

# Abbreviated ADS-B Exchange-style CSV columns -> AircraftState fields.
# Confirmed against data/lynchburg_adsb.csv: h=hex, la/lo=position, ab/ag=baro
# and geometric altitude (ft), gs=ground speed (kt), tr=track (deg), f=callsign,
# sq=squawk, c=emitter category, n=NIC, np=NACp, og=on ground. CLAUDE.md's
# provisional table guessed nb for NIC, but the file has both n and nb, and nb
# is NIC-baro (a 0/1 flag): the first row reads n=8, nb=1.
_CSV_COLUMNS = {
    "icao24": "h",
    "lat": "la",
    "lon": "lo",
    "alt_baro_ft": "ab",
    "alt_geom_ft": "ag",
    "ground_speed_kt": "gs",
    "track_deg": "tr",
    "callsign": "f",
    "squawk": "sq",
    "emitter_category": "c",
    "nic": "n",
    "nac_p": "np",
    "on_ground": "og",
    "timestamp": "timestamp",
}
_REQUIRED_CSV = ("h", "la", "lo", "timestamp")


def load_states(path: str | Path) -> Iterator[AircraftState]:
    """Yield one :class:`AircraftState` per usable row of ``path``.

    Raises:
        FileNotFoundError: ``path`` does not exist (raised when iteration starts).
        ValueError: A required column is missing, the format is unsupported, or
            a timestamp does not parse as tz-aware UTC.
    """
    source = Path(path)
    suffix = source.suffix.lower()
    if suffix == ".json":
        yield from _from_records(_json_rows(source), source.name)
    elif suffix == ".csv":
        yield from _from_records(_csv_rows(source), source.name)
    elif suffix == ".parquet":
        yield from _from_records(_parquet_rows(source), source.name)
    else:
        raise ValueError(f"unsupported ADS-B file type: {source.suffix or source.name}")


def _json_rows(source: Path) -> Iterator[dict[str, Any]]:
    rows = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError(f"{source.name}: expected a JSON list of state records")
    for row in rows:
        if isinstance(row, dict):
            yield row


def _csv_rows(source: Path) -> Iterator[dict[str, Any]]:
    with open(source, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in _REQUIRED_CSV if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{source.name}: missing required column(s) {missing}")
        for line, raw in enumerate(reader, start=2):
            row: dict[str, Any] = {f: raw.get(col) for f, col in _CSV_COLUMNS.items()}
            row["source_row_id"] = f"{source.name}:{line}"
            yield row


def _parquet_rows(source: Path) -> Iterator[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq  # type: ignore[import-not-found]  # eda extra
    except ImportError as exc:
        raise ValueError("reading Parquet needs pyarrow: pip install -e '.[eda]'") from exc
    for index, row in enumerate(pq.read_table(source).to_pylist()):
        row.setdefault("source_row_id", f"{source.name}:{index}")
        yield row


def _from_records(rows: Iterable[Mapping[str, Any]], name: str) -> Iterator[AircraftState]:
    for index, row in enumerate(rows):
        state = _to_state(row, f"{name}:{index}")
        if state is not None:
            yield state


def parse_utc(value: Any) -> datetime:
    """Parse an ISO-8601 string or datetime into tz-aware UTC.

    Raises:
        ValueError: The value is missing, unparseable, or has no timezone.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    else:
        raise ValueError(f"timestamp is missing or not a string: {value!r}")
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp has no timezone, refusing to guess: {value!r}")
    return parsed.astimezone(UTC)


def _to_state(row: Mapping[str, Any], fallback_id: str) -> AircraftState | None:
    """One row -> state, or None when the row is individually unusable."""
    lat = _float(row.get("lat"))
    lon = _float(row.get("lon"))
    icao = _text(row.get("icao24"))
    if lat is None or lon is None or icao is None:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return AircraftState(
        icao24=icao.lower(),
        timestamp=parse_utc(row.get("timestamp")),
        lat=lat,
        lon=lon,
        alt_baro_ft=_float(row.get("alt_baro_ft")),
        alt_geom_ft=_float(row.get("alt_geom_ft")),
        ground_speed_kt=_float(row.get("ground_speed_kt")),
        track_deg=_float(row.get("track_deg")),
        callsign=_text(row.get("callsign")),
        squawk=_text(row.get("squawk")),
        emitter_category=_text(row.get("emitter_category")),
        nic=_int(row.get("nic")),
        nac_p=_int(row.get("nac_p")),
        on_ground=_bool(row.get("on_ground")),
        source_row_id=_text(row.get("source_row_id")) or fallback_id,
    )


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None  # "ground", "", and other non-numeric altitude markers
    return out if out == out and abs(out) != float("inf") else None


def _int(value: Any) -> int | None:
    out = _float(value)
    return int(out) if out is not None else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    out = str(value).strip()
    return out or None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "ground"}
