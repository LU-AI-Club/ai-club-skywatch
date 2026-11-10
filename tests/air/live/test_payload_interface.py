"""Contract tests for the two Spine A helpers.

Mirrors tests/air/live/test_live_spine.py: pins the signatures and the reason
names, so the people writing A4b, A4c and A4d work against a fixed interface.

Both helpers are implemented now -- ``unusable_reason`` in A3b and
``observation_from_row`` in A3a -- so the stub-raises check that used to live
here is gone. What remains is the shape of the interface plus the one behavior
the whole live path depends on: a bad row returns rather than raising. The
field-by-field behavior is covered by the owning tickets' own tests, and the
parity test (A4d) is what proves the mapping matches the CSV path.
"""

from __future__ import annotations

import inspect

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


def test_observation_from_row_never_raises():
    """Whatever the row, it returns rather than raising.

    Not a nicety: the live reader sees whatever the feed produced, and one
    malformed record must not be able to kill a whole window.
    """
    for row in ({}, {"entity_id": None}, {"entity_id": "icao24:a1b2c3", "payload": "not json"}):
        assert observation_from_row(row) is None


def test_unusable_reason_agrees_with_the_mapper():
    """The two helpers must not disagree about which rows are usable.

    They are split so the abstain rules live in one place; if a row has a
    reason, the mapper has to skip it, and if it has none, the mapper has to
    produce something. A second copy of the rules inside the mapper would show
    up here.
    """
    usable = {
        "entity_id": "icao24:a1b2c3",
        "observed_at": "2026-09-01T00:00:00+00:00",
        "latitude": 37.0,
        "longitude": -79.0,
        "payload": {},
    }
    assert unusable_reason(usable) is None
    assert observation_from_row(usable) is not None

    for missing in ("entity_id", "observed_at", "latitude"):
        row = dict(usable)
        row.pop(missing)
        assert unusable_reason(row) is not None, f"{missing} should be a reason"
        assert observation_from_row(row) is None, f"{missing} should be skipped"
