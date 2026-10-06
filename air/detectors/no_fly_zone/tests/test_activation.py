"""Stream E tests - logic/activation.py.

Firing case, non-firing case, and the naive-timestamp guard. The zone mirrors
fixture TFR-6/1234 in fixtures/airspace/klyh-150nm.geojson.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from shapely.geometry import box

from ..logic.activation import is_active
from ..types import Activation, ActivationState, AirspaceZone, Datum, TimeWindow, ZoneType


def make_tfr(**overrides: Any) -> AirspaceZone:
    """Fixture zone TFR-6/1234: SFC-5000 MSL, live 2026-09-22 19:00Z to 09-23 01:30Z."""
    base: dict[str, Any] = {
        "zone_id": "TFR-6/1234",
        "name": "Hand-built TFR with an explicit window (test)",
        "zone_type": ZoneType.TFR,
        "geometry": box(-79.30, 37.20, -79.22, 37.26),
        "floor_ft": 0.0,
        "floor_datum": Datum.SFC,
        "ceiling_ft": 5000.0,
        "ceiling_datum": Datum.MSL,
        "activation": Activation.WINDOW,
        "active_windows": (
            TimeWindow(
                start=datetime(2026, 9, 22, 19, 0, tzinfo=UTC),
                end=datetime(2026, 9, 23, 1, 30, tzinfo=UTC),
            ),
        ),
    }
    base.update(overrides)
    return AirspaceZone(**base)


def test_tfr_inside_its_window_is_active() -> None:
    """2026-09-22T20:15Z falls inside the fixture TFR window 19:00Z-01:30Z."""
    result = is_active(make_tfr(), datetime(2026, 9, 22, 20, 15, tzinfo=UTC))
    assert result.state is ActivationState.ACTIVE
    assert result.zone_id == "TFR-6/1234"
    assert "1900Z-0130Z" in result.basis


def test_tfr_before_its_window_is_inactive() -> None:
    """14:00Z is five hours early, so the same zone is cold."""
    result = is_active(make_tfr(), datetime(2026, 9, 22, 14, 0, tzinfo=UTC))
    assert result.state is ActivationState.INACTIVE


def test_naive_timestamp_is_rejected() -> None:
    """A timestamp with no timezone is a caller bug, not something to coerce."""
    with pytest.raises(ValueError):
        is_active(make_tfr(), datetime(2026, 9, 22, 20, 15))