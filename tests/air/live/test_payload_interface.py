"""Contract tests for the two Spine A helpers, before their bodies exist.

Mirrors tests/air/live/test_live_spine.py: pin the signatures on day 1 so the
people writing A4b, A4c and A4d can work against them while A3a and A3b are
still being written, and so CI is green from the moment the stubs land.

These assert the shape of the interface, not the behavior. The owning tickets
bring the real fixture tests.
"""

from __future__ import annotations

import inspect

import pytest

from air.live.payload import observation_from_row
from air.live.row_validation import REASONS, unusable_reason


def test_observation_from_row_takes_one_row():
    """One row in, one observation (or None) out. No connection, no window."""
    signature = inspect.signature(observation_from_row)
    assert list(signature.parameters) == ["row"]


def test_unusable_reason_takes_one_row():
    signature = inspect.signature(unusable_reason)
    assert list(signature.parameters) == ["row"]


def test_the_reasons_are_named_not_prose():
    """Tests and log counters key off these, so they are part of the contract."""
    assert "MISSING_ENTITY" in REASONS
    assert "MISSING_TIME" in REASONS
    assert "MISSING_POSITION" in REASONS
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in REASONS.items())


def test_stubs_raise_until_their_owners_implement_them():
    row = {"entity_id": "icao24:a1b2c3", "payload": {}}
    #with pytest.raises(NotImplementedError):
    #    unusable_reason(row) #this was removed when I implemented this function
    with pytest.raises(NotImplementedError):
        observation_from_row(row)
