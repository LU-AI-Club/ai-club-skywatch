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

from collections.abc import Iterator
from pathlib import Path

from ..types import AircraftState


def load_states(path: str | Path) -> Iterator[AircraftState]:
    """Yield one :class:`AircraftState` per usable row of ``path``."""
    raise NotImplementedError("stream A: adsb_loader")
