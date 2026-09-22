"""Stream A tests - ingest/adsb_loader.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ..ingest.adsb_loader import load_states
from .conftest import TRACKS_FILE

SKIP = pytest.mark.skip(reason="stream A: not implemented")


@SKIP
def test_loads_every_usable_row() -> None:
    """Five fixture rows in, five AircraftState out, annotation keys ignored."""
    states = list(load_states(TRACKS_FILE))
    assert len(states) == 5
    assert states[0].icao24 == 'a1b2c3'
    assert states[0].timestamp.tzinfo is not None


@SKIP
def test_skips_a_row_with_no_position() -> None:
    """A row missing lat/lon is skipped, not raised on - one bad row must not
    kill an hour of data."""
    pytest.fail('write me: feed a row with null lat/lon, assert it is skipped')
