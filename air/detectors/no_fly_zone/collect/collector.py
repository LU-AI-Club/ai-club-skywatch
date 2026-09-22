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

from pathlib import Path


def collect(url: str, out_dir: str | Path) -> None:
    """Poll ``url`` and write hourly Parquet into ``out_dir``. Runs forever."""
    raise NotImplementedError("stream I: collector")
