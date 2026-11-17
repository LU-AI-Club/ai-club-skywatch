"""Stream E - is the zone live right now?

A restricted area that is cold is not a violation. Prohibited areas are always
on; MOAs and restricted areas run published schedules; TFRs carry explicit
start/end windows; some zones are NOTAM-activated and we simply cannot know.

Inputs
------
zone:
    Supplies ``activation`` and ``active_windows``.
ts:
    The observation timestamp. Must be tz-aware UTC; a naive datetime is a bug
    in the caller, not something to coerce here.

Outputs
-------
An :class:`ActivationResult` carrying the :class:`ActivationState`, the
``zone_id``, and a human-readable ``basis`` such as ``"always active"`` or
``"TFR window 1900Z-0130Z"``. The basis lands in the Detection explanation, so
write it for an analyst, not for a log.

Failure causes
--------------
ValueError
    ``ts`` is naive rather than tz-aware UTC.

:attr:`Activation.NOTAM` returns :attr:`ActivationState.UNKNOWN`, never a
guess. UNKNOWN is not a pass: it caps severity downstream at
``cfg["severity"]["unknown_activation_cap"]``. Saying "we could not tell" is a
real answer and the honest one.

Notes
-----
Windows are half-open ``[start, end)`` per :class:`TimeWindow`, so a state
exactly at ``end`` is outside. Windows crossing midnight UTC are ordinary
ranges, not a special case.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from math import acos, asin, atan, cos, degrees, radians, sin, tan
from zoneinfo import ZoneInfo

from ..types import (
    Activation,
    ActivationResult,
    ActivationState,
    AirspaceZone,
    RecurringWindow,
)


def _solar_time(
    day: date, latitude: float, longitude: float, timezone: ZoneInfo, *, sunrise: bool
) -> datetime | None:
    """Approximate sunrise or sunset in local time using NOAA's solar equations."""
    day_number = day.timetuple().tm_yday
    longitude_hour = longitude / 15.0
    approximate = day_number + ((6.0 if sunrise else 18.0) - longitude_hour) / 24.0
    mean_anomaly = 0.9856 * approximate - 3.289
    true_longitude = (
        mean_anomaly
        + 1.916 * sin(radians(mean_anomaly))
        + 0.020 * sin(2 * radians(mean_anomaly))
        + 282.634
    ) % 360.0
    right_ascension = degrees(atan(0.91764 * tan(radians(true_longitude)))) % 360.0
    right_ascension += (int(true_longitude / 90.0) * 90.0) - (
        int(right_ascension / 90.0) * 90.0
    )
    right_ascension /= 15.0
    sin_declination = 0.39782 * sin(radians(true_longitude))
    cos_declination = cos(asin(sin_declination))
    cos_hour_angle = (
        cos(radians(90.833)) - sin_declination * sin(radians(latitude))
    ) / (cos_declination * cos(radians(latitude)))
    if cos_hour_angle < -1.0 or cos_hour_angle > 1.0:
        return None

    hour_angle = degrees(acos(cos_hour_angle))
    if sunrise:
        hour_angle = 360.0 - hour_angle
    local_mean_time = hour_angle / 15.0 + right_ascension - 0.06571 * approximate - 6.622
    utc_hour = (local_mean_time - longitude_hour) % 24.0
    utc_midnight = datetime.combine(day, time.min, tzinfo=UTC)
    return (utc_midnight + timedelta(hours=utc_hour)).astimezone(timezone)


def _in_annual_range(day: date, start: tuple[int, int], end: tuple[int, int]) -> bool:
    month_day = (day.month, day.day)
    if start <= end:
        return start <= month_day <= end
    return month_day >= start or month_day <= end


def _recurring_window_basis(
    window: RecurringWindow, day: date, timezone: ZoneInfo, latitude: float, longitude: float
) -> tuple[datetime | None, datetime | None, bool]:
    """Resolve a recurring window's local bounds and whether it is all-day."""
    if window.all_day:
        return None, None, True
    if window.start_sunrise:
        start = _solar_time(day, latitude, longitude, timezone, sunrise=True)
    elif window.start_time is not None:
        start = datetime.combine(day, window.start_time, tzinfo=timezone)
    else:
        start = None

    if window.end_sunset:
        end = _solar_time(day, latitude, longitude, timezone, sunrise=False)
    elif window.end_time is not None:
        end = datetime.combine(day, window.end_time, tzinfo=timezone)
    else:
        end = None
    return start, end, False


def _scheduled_window(
    zone: AirspaceZone, window: RecurringWindow, local_ts: datetime, timezone: ZoneInfo
) -> bool:
    day = local_ts.date()
    if window.weekdays and day.weekday() not in window.weekdays:
        return False
    if (
        window.start_month_day is not None
        and window.end_month_day is not None
        and not _in_annual_range(day, window.start_month_day, window.end_month_day)
    ):
        return False

    centroid = zone.geometry.centroid
    start, end, all_day = _recurring_window_basis(
        window, day, timezone, centroid.y, centroid.x
    )
    if all_day:
        return True
    if start is None or end is None:
        return False
    if end <= start:
        end += timedelta(days=1)
    return start <= local_ts < end


def _active_schedule_basis(
    zone: AirspaceZone, window: RecurringWindow, local_ts: datetime, timezone: ZoneInfo
) -> str:
    if window.all_day:
        return f"published all-day schedule ({timezone.key})"
    centroid = zone.geometry.centroid
    start, end, _ = _recurring_window_basis(
        window, local_ts.date(), timezone, centroid.y, centroid.x
    )
    if start is not None and end is not None:
        return f"published local-time schedule {start:%H%M}-{end:%H%M} ({timezone.key})"
    return f"published schedule ({timezone.key})"


def is_active(zone: AirspaceZone, ts: datetime) -> ActivationResult:
    """Decide whether ``zone`` was live at ``ts``."""
    # 1. A timestamp with no timezone is a bug in the caller. Refuse it loudly.
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"is_active needs a tz-aware UTC timestamp, got naive {ts!r}")

    # 2. Prohibited areas and anything else marked ALWAYS are always live.
    if zone.activation is Activation.ALWAYS:
        return ActivationResult(ActivationState.ACTIVE, zone.zone_id, "always active")

    # 3. NOTAM-activated zones: we cannot know, so we say so. Never guess.
    if zone.activation is Activation.NOTAM:
        return ActivationResult(
            ActivationState.UNKNOWN,
            zone.zone_id,
            "NOTAM-activated; live status not known to this detector",
        )

    # 4. WINDOW or SCHEDULED with no windows listed: no schedule is not the
    #    same as "off", so report UNKNOWN rather than INACTIVE.
    if not zone.active_windows and not zone.recurring_windows:
        return ActivationResult(
            ActivationState.UNKNOWN,
            zone.zone_id,
            f"{zone.activation.value} zone with no published windows",
        )

    # 5. Live if ts falls inside any fixed window. Half-open: start <= ts < end.
    for window in zone.active_windows:
        if window.start <= ts < window.end:
            basis = (
                f"{zone.zone_type.value} window "
                f"{window.start:%H%M}Z-{window.end:%H%M}Z"
            )
            return ActivationResult(ActivationState.ACTIVE, zone.zone_id, basis)

    if zone.recurring_windows:
        timezone = ZoneInfo(zone.schedule_timezone)
        local_ts = ts.astimezone(timezone)
        for recurring_window in zone.recurring_windows:
            if _scheduled_window(zone, recurring_window, local_ts, timezone):
                basis = _active_schedule_basis(
                    zone, recurring_window, local_ts, timezone
                )
                # Hours published as "by NOTAM" or "intermittent" only bound
                # when the zone may be in use. Inside them we still cannot
                # tell, so say so rather than call it live.
                if zone.unknown_within_schedule:
                    return ActivationResult(
                        ActivationState.UNKNOWN,
                        zone.zone_id,
                        f"within {basis}, but in use only by NOTAM or intermittently",
                    )
                return ActivationResult(ActivationState.ACTIVE, zone.zone_id, basis)

    if zone.unknown_outside_schedule:
        return ActivationResult(
            ActivationState.UNKNOWN,
            zone.zone_id,
            "outside published schedule; additional activation may occur by NOTAM",
        )

    # 6. Windows exist but none covers ts: the zone was cold.
    return ActivationResult(
        ActivationState.INACTIVE,
        zone.zone_id,
        f"outside all {len(zone.active_windows) + len(zone.recurring_windows)} "
        "published window(s)",
    )