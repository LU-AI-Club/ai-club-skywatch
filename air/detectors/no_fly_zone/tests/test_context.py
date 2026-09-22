"""Stream F tests - logic/context.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ..logic.context import gather_signals
from .conftest import make_state

SKIP = pytest.mark.skip(reason="stream F: not implemented")


@SKIP
def test_emergency_squawk_produces_a_weighted_signal() -> None:
    """7700 yields one signal whose weight comes from config, not a literal."""
    pytest.fail('write me: make_state(squawk=7700), assert one signal named '
                'emergency_squawk carrying the configured weight')


@SKIP
def test_ordinary_state_produces_no_signals() -> None:
    """A VFR squawk on a civil airframe yields an empty list, which is the normal
    case and not a failure."""
    pytest.fail('write me: default state, assert gather_signals() == []')
