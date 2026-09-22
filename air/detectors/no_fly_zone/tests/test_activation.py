"""Stream E tests - logic/activation.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ..logic.activation import is_active
from ..types import ActivationState

SKIP = pytest.mark.skip(reason="stream E: not implemented")


@SKIP
def test_tfr_inside_its_window_is_active() -> None:
    """2026-09-22T20:15Z falls inside the fixture TFR window 19:00Z-01:30Z."""
    pytest.fail('write me: assert state is ActivationState.ACTIVE and the '
                'basis names the window')


@SKIP
def test_tfr_before_its_window_is_inactive() -> None:
    """14:00Z is five hours early, so the same zone is cold."""
    pytest.fail('write me: assert state is ActivationState.INACTIVE')
