"""Stream Lead tests - logic/detector.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ..logic.detector import run
from .conftest import make_state

SKIP = pytest.mark.skip(reason="stream Lead: not implemented")


@SKIP
def test_fixture_track_yields_the_two_expected_detections() -> None:
    """fixture-1 and fixture-3 fire; the other three exit. See fixtures/README.md."""
    pytest.fail('write me: run the 5 fixture states, assert 2 detections, '
                'one P-901 and one TFR-6/1234')


@SKIP
def test_on_ground_state_never_reaches_geometry() -> None:
    """With filters.drop_on_ground true, a taxiing aircraft exits as ON_GROUND
    before any polygon test runs."""
    pytest.fail('write me: make_state(on_ground=True), assert no detection')
