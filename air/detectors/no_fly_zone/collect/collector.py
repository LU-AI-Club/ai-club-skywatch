"""Stream I - live ADS-B collector. A SEPARATE PROCESS from the detector.

Polls our own receiver (dump1090 / AirNav) at ``sampling.target_hz`` and writes
hourly Parquet. The detector never talks to a network or a receiver; it reads
the files this produces. That separation is what keeps every detector function
pure and testable.

Inputs
------
url:
    Receiver endpoint, e.g. a dump1090 ``aircraft.json``.
out_dir:
    Directory for hourly Parquet files. Created if absent. Name files so they
    sort chronologically, e.g. ``states-2026-09-22T14.parquet``.

Outputs
-------
``None``. The side effect is the files. This is the one module in the package
allowed to do network and disk I/O in normal operation.

Failure causes
--------------
OSError / connection errors
    Receiver unreachable. Log, back off, keep running - a collector that dies
    on one dropped connection loses the rest of the hour.
PermissionError
    ``out_dir`` not writable.

Never crash the loop on a single malformed poll. A gap in the data is
recoverable; a dead collector is not.

Notes
-----
Write the current hour to a temp name and rename on roll-over, so the detector
never reads a half-written file. Gaps longer than ``sampling.max_gap_sec``
break a track for dwell purposes, so record actual poll timestamps rather than
assuming a perfect 1 Hz cadence.
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

SCHEMA = pa.schema([
    ("icao24", pa.string()),
    ("timestamp", pa.timestamp("us", tz="UTC")),
    ("lat", pa.float64()),
    ("lon", pa.float64()),
    ("alt_baro_ft", pa.float64()),
    ("alt_geom_ft", pa.float64()),
    ("ground_speed_kt", pa.float64()),
    ("track_deg", pa.float64()),
    ("callsign", pa.string()),
    ("squawk", pa.string()),
    ("emitter_category", pa.string()),
    ("nic", pa.int32()),
    ("nac_p", pa.int32()),
    ("on_ground", pa.bool_()),
    ("source_row_id", pa.string()),
])


def hour_filename(hour: datetime) -> str:
    """Name that sorts chronologically, e.g. states-2026-09-22T14.parquet."""
    return f"states-{hour:%Y-%m-%dT%H}.parquet"


def write_hour(rows: list[dict[str, Any]], out_dir: str | Path, hour: datetime) -> Path:
    """Write ``rows`` to the file for ``hour`` and return its path.

    Writes to a temp name first, then renames, so a reader never sees a
    half-written file. Keys missing from a row are stored as null.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / hour_filename(hour)
    temp = out_dir / (final.name + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), temp)
    os.replace(temp, final)
    return final


def collect(url: str, out_dir: str | Path) -> None:
    """Poll ``url`` and write hourly Parquet into ``out_dir``. Runs forever."""
    raise NotImplementedError("stream I: collector")