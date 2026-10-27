"""Stream E tests - recurring schedules in logic/activation.py.

"Mon-Fri 1300-2200Z" is the canonical case: inside, outside, and both edges of
the half-open window, on both the hour and the day axis. 2026-09-21 is a Monday.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from shapely.geometry import box

from air.detectors.no_fly_zone.logic.activation import (
    is_active,
    parse_schedule,
    schedule_is_live,
)
from air.detectors.no_fly_zone.types import (
    Activation,
    ActivationState,
    AirspaceZone,
    Datum,
    TimeWindow,
    ZoneType,
)

WEEKDAYS = parse_schedule("Mon–Fri 1300–2200Z")  # en dashes, as published


def make_moa(**overrides: Any) -> AirspaceZone:
    """A SCHEDULED MOA published as live Mon-Fri 1300-2200Z."""
    base: dict[str, Any] = {
        "zone_id": "SCHED-MOA",
        "name": "Hand-built MOA with recurring hours (test)",
        "zone_type": ZoneType.MOA,
        "geometry": box(-79.30, 37.20, -79.22, 37.26),
        "floor_ft": 8000.0,
        "floor_datum": Datum.MSL,
        "ceiling_ft": 18000.0,
        "ceiling_datum": Datum.FL,
        "activation": Activation.SCHEDULED,
        "schedule": "Mon–Fri 1300–2200Z",
    }
    base.update(overrides)
    return AirspaceZone(**base)


def at(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    """``day`` days after Monday 2026-09-21, at the given UTC time."""
    return datetime(2026, 9, 21, hour, minute, second, tzinfo=UTC) + timedelta(days=day)


def test_inside_hours_on_a_weekday_is_live() -> None:
    assert schedule_is_live(WEEKDAYS, at(2, 17, 30))  # Wednesday 1730Z


def test_outside_hours_on_a_weekday_is_cold() -> None:
    assert not schedule_is_live(WEEKDAYS, at(2, 8, 0))   # Wednesday 0800Z
    assert not schedule_is_live(WEEKDAYS, at(2, 23, 0))  # Wednesday 2300Z


def test_weekend_inside_hours_is_cold() -> None:
    assert not schedule_is_live(WEEKDAYS, at(5, 15, 0))  # Saturday
    assert not schedule_is_live(WEEKDAYS, at(6, 15, 0))  # Sunday


def test_start_edge_is_live() -> None:
    """Half-open window: exactly 1300Z is inside, one second before is not."""
    assert schedule_is_live(WEEKDAYS, at(0, 13, 0))
    assert not schedule_is_live(WEEKDAYS, at(0, 12, 59, 59))


def test_end_edge_is_cold() -> None:
    """Half-open window: exactly 2200Z is outside, one second before is not."""
    assert not schedule_is_live(WEEKDAYS, at(4, 22, 0))
    assert schedule_is_live(WEEKDAYS, at(4, 21, 59, 59))


def test_day_edges() -> None:
    """Monday is the first live day and Friday the last."""
    assert schedule_is_live(WEEKDAYS, at(0, 15, 0))      # Monday
    assert schedule_is_live(WEEKDAYS, at(4, 15, 0))      # Friday
    assert not schedule_is_live(WEEKDAYS, at(-1, 15, 0))  # the Sunday before


def test_non_utc_timestamp_is_converted() -> None:
    """0900 at UTC-5 is 1400Z, inside the window."""
    est = timezone(timedelta(hours=-5))
    assert schedule_is_live(WEEKDAYS, datetime(2026, 9, 21, 9, 0, tzinfo=est))


def test_overnight_window_belongs_to_its_start_day() -> None:
    """Friday's 2200-0400Z window runs into Saturday; Monday 0300Z is cold."""
    nights = parse_schedule("Mon-Fri 2200-0400Z")
    assert schedule_is_live(nights, at(4, 23, 0))      # Friday night
    assert schedule_is_live(nights, at(5, 3, 0))       # Saturday 0300Z
    assert not schedule_is_live(nights, at(5, 4, 0))   # Saturday 0400Z end edge
    assert not schedule_is_live(nights, at(5, 22, 0))  # Saturday night
    assert not schedule_is_live(nights, at(0, 3, 0))   # Monday 0300Z (Sunday off)


@pytest.mark.parametrize(
    ("text", "live_days"),
    [
        ("Daily 0000-2400Z", {0, 1, 2, 3, 4, 5, 6}),
        ("Sat 0800-1200Z", {5}),
        ("Mon-Wed,Fri 0800-1200Z", {0, 1, 2, 4}),
        ("Fri-Mon 0800-1200Z", {4, 5, 6, 0}),
        ("sat, sun 0800-1200z", {5, 6}),
    ],
)
def test_day_forms(text: str, live_days: set[int]) -> None:
    assert parse_schedule(text).days == live_days


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Mon-Fri",
        "Mon-Fri 1300-2200",     # no Z: local time is not supported
        "Funday 1300-2200Z",
        "Mon-Fri 1360-2200Z",
        "Mon-Fri 2500-2600Z",
        "Mon-Fri 1300-1300Z",
        "Mon-Wed-Fri 1300-2200Z",
    ],
)
def test_malformed_schedule_is_rejected(text: str) -> None:
    with pytest.raises(ValueError):
        parse_schedule(text)


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError):
        schedule_is_live(WEEKDAYS, datetime(2026, 9, 21, 15, 0))


# ---------------------------------------------------------------- is_active


def test_is_active_inside_schedule_is_active() -> None:
    result = is_active(make_moa(), at(2, 17, 30))  # Wednesday 1730Z
    assert result.state is ActivationState.ACTIVE
    assert result.zone_id == "SCHED-MOA"
    assert "1300\u20132200Z" in result.basis


def test_is_active_outside_schedule_is_inactive() -> None:
    assert is_active(make_moa(), at(5, 15, 0)).state is ActivationState.INACTIVE  # Saturday
    assert is_active(make_moa(), at(2, 23, 0)).state is ActivationState.INACTIVE  # 2300Z


def test_is_active_schedule_edges() -> None:
    """1300Z opens the zone; 2200Z has already closed it."""
    assert is_active(make_moa(), at(0, 13, 0)).state is ActivationState.ACTIVE
    assert is_active(make_moa(), at(0, 22, 0)).state is ActivationState.INACTIVE


def test_schedule_overrides_dated_windows() -> None:
    """Recurring hours, not a stale dated window, decide a SCHEDULED zone."""
    stale = TimeWindow(start=at(5, 0), end=at(6, 0))  # Saturday 0000Z-Sunday 0000Z
    zone = make_moa(active_windows=(stale,))
    assert is_active(zone, at(5, 15, 0)).state is ActivationState.INACTIVE


def test_unparseable_schedule_is_unknown() -> None:
    """A schedule we cannot read is UNKNOWN, never a guess and never a crash."""
    result = is_active(make_moa(schedule="weekdays, mostly"), at(2, 17, 30))
    assert result.state is ActivationState.UNKNOWN
    assert "weekdays, mostly" in result.basis


def test_schedule_ignored_for_window_zones() -> None:
    """Only SCHEDULED zones read ``schedule``; a WINDOW zone uses its windows."""
    zone = make_moa(activation=Activation.WINDOW)
    assert is_active(zone, at(2, 17, 30)).state is ActivationState.UNKNOWN
