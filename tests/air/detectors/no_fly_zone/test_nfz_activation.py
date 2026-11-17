"""Stream E tests - logic/activation.py.

Firing case, non-firing case, and the naive-timestamp guard. The zone mirrors
fixture TFR-6/1234 in fixtures/airspace/klyh-150nm.geojson.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from shapely.geometry import box

from air.detectors import no_fly_zone
from air.detectors.no_fly_zone.ingest.airspace_loader import load_zones
from air.detectors.no_fly_zone.logic.activation import is_active
from air.detectors.no_fly_zone.types import (
    Activation,
    ActivationState,
    AirspaceZone,
    Datum,
    TimeWindow,
    ZoneType,
)

LOCAL_AIRSPACE_FILE = (
    Path(no_fly_zone.__file__).resolve().parent
    / "fixtures"
    / "airspace"
    / "klyh-local-faa.geojson"
)


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


def _local_zones() -> dict[str, AirspaceZone]:
    return {zone.zone_id: zone for zone in load_zones(LOCAL_AIRSPACE_FILE)}


def test_local_airspace_has_known_activation_for_thirteen_of_fifteen_zones() -> None:
    zones = _local_zones()

    assert len(zones) == 15
    assert sum(zone.activation is not Activation.NOTAM for zone in zones.values()) == 13


def test_farmville_schedule_is_active_weekdays_and_unknown_outside() -> None:
    zone = _local_zones()["FARMVILLE MOA"]
    inside = is_active(zone, datetime(2026, 11, 18, 15, tzinfo=UTC))
    before_local_start = is_active(zone, datetime(2026, 11, 18, 12, 30, tzinfo=UTC))
    outside = is_active(zone, datetime(2026, 11, 18, 23, tzinfo=UTC))
    weekend = is_active(zone, datetime(2026, 11, 21, 15, tzinfo=UTC))

    assert inside.state is ActivationState.ACTIVE
    assert "0800-1700" in inside.basis
    assert before_local_start.state is ActivationState.UNKNOWN
    assert outside.state is ActivationState.UNKNOWN
    assert weekend.state is ActivationState.UNKNOWN


def test_evers_schedule_runs_until_sunset_and_is_unknown_outside() -> None:
    zone = _local_zones()["EVERS CENTER MOA"]
    inside = is_active(zone, datetime(2026, 11, 18, 15, tzinfo=UTC))
    before_local_start = is_active(zone, datetime(2026, 11, 18, 8, tzinfo=UTC))
    outside = is_active(zone, datetime(2026, 11, 19, 1, tzinfo=UTC))

    assert inside.state is ActivationState.ACTIVE
    assert "America/New_York" in inside.basis
    assert before_local_start.state is ActivationState.UNKNOWN
    assert outside.state is ActivationState.UNKNOWN


def test_barfoot_schedule_runs_sunrise_to_sunset() -> None:
    zone = _local_zones()["BARFOOT 1 MOA"]
    inside = is_active(zone, datetime(2026, 11, 18, 15, tzinfo=UTC))
    before_sunrise = is_active(zone, datetime(2026, 11, 18, 10, tzinfo=UTC))
    outside = is_active(zone, datetime(2026, 11, 19, 5, tzinfo=UTC))

    assert inside.state is ActivationState.ACTIVE
    assert before_sunrise.state is ActivationState.INACTIVE
    assert outside.state is ActivationState.INACTIVE


def test_r6602a_schedule_is_seasonal_and_unknown_outside() -> None:
    zone = _local_zones()["R-6602A"]
    inside = is_active(zone, datetime(2026, 7, 1, 16, tzinfo=UTC))
    outside = is_active(zone, datetime(2026, 4, 1, 16, tzinfo=UTC))
    before_local_season = is_active(zone, datetime(2026, 5, 1, 3, 30, tzinfo=UTC))

    assert inside.state is ActivationState.ACTIVE
    assert outside.state is ActivationState.UNKNOWN
    assert before_local_season.state is ActivationState.UNKNOWN