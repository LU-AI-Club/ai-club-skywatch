"""Stream I tests - collect/collector.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from ..collect.collector import collect, write_hour

SKIP = pytest.mark.skip(reason="stream I: not implemented")


@SKIP
def test_writes_an_hourly_parquet_file() -> None:
    """One hour of polls lands in one Parquet file, named so files sort by time."""
    pytest.fail('write me: fake the receiver, assert a .parquet appears in out_dir')


@SKIP
def test_survives_an_unreachable_receiver() -> None:
    """A refused connection is logged and retried, never fatal - a dead collector
    loses far more data than one dropped poll."""
    pytest.fail('write me: point collect at a closed port, assert it backs off')


def test_write_hour_names_file_by_hour_and_leaves_no_temp(tmp_path: Path) -> None:
    rows = [{
        "icao24": "a1b2c3",
        "timestamp": datetime(2026, 9, 22, 14, 5, tzinfo=UTC),
        "lat": 37.4,
        "lon": -79.2,
        "alt_baro_ft": 4850.0,
    }]
    path = write_hour(rows, tmp_path, datetime(2026, 9, 22, 14, tzinfo=UTC))

    assert path.name == "states-2026-09-22T14.parquet"
    assert list(tmp_path.glob("*.tmp")) == []
    table = pq.read_table(path)
    assert table.num_rows == 1
    assert table.column("icao24").to_pylist() == ["a1b2c3"]