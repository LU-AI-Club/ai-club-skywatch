"""Stream I tests - collect/collector.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ...air.detectors.no_fly_zone.collect.collector import collect

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
