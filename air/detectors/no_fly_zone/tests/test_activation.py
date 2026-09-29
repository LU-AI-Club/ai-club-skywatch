"""Stream E tests - logic/activation.py."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from ..ingest.airspace_loader import load_zones
from ..logic.activation import is_active
from ..types import Activation, ActivationState
from .conftest import AIRSPACE_FILE


def _zone(zone_id: str):  # type: ignore[no-untyped-def]
    return next(z for z in load_zones(AIRSPACE_FILE) if z.zone_id == zone_id)


def test_tfr_inside_its_window_is_active() -> None:
    """2026-09-22T20:15Z falls inside the fixture TFR window 19:00Z-01:30Z."""
    result = is_active(_zone("TFR-6/1234"), datetime(2026, 9, 22, 20, 15, tzinfo=UTC))
    assert result.state is ActivationState.ACTIVE
    assert "TFR window" in result.basis and "1900Z" in result.basis


def test_tfr_before_its_window_is_inactive() -> None:
    """14:00Z is five hours early, so the same zone is cold."""
    result = is_active(_zone("TFR-6/1234"), datetime(2026, 9, 22, 14, 0, tzinfo=UTC))
    assert result.state is ActivationState.INACTIVE


def test_window_end_is_exclusive() -> None:
    result = is_active(_zone("TFR-6/1234"), datetime(2026, 9, 23, 1, 30, tzinfo=UTC))
    assert result.state is ActivationState.INACTIVE


def test_notam_zone_is_unknown_never_assumed_active() -> None:
    """Missing NOTAM data is not a pass and not a fail: it is UNKNOWN."""
    zone = replace(_zone("P-901"), activation=Activation.NOTAM)
    result = is_active(zone, datetime(2026, 9, 22, 20, 15, tzinfo=UTC))
    assert result.state is ActivationState.UNKNOWN


def test_scheduled_zone_with_no_windows_is_unknown() -> None:
    zone = replace(_zone("LYNCHBURG-MOA"), active_windows=())
    result = is_active(zone, datetime(2026, 9, 22, 20, 15, tzinfo=UTC))
    assert result.state is ActivationState.UNKNOWN


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        is_active(_zone("P-901"), datetime(2026, 9, 22, 20, 15))
