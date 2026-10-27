"""Stream E - is the zone live right now?

A restricted area that is cold is not a violation. Prohibited areas are always
on; MOAs and restricted areas run published schedules; TFRs carry explicit
start/end windows; some zones are NOTAM-activated and we simply cannot know.

Inputs
------
zone:
    Supplies ``activation``, ``active_windows`` and, for SCHEDULED zones,
    an optional recurring ``schedule``.
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
real answer and the honest one. A SCHEDULED zone whose ``schedule`` text
cannot be parsed is also UNKNOWN, with the parse error in the basis.

Notes
-----
Windows are half-open ``[start, end)`` per :class:`TimeWindow`, so a state
exactly at ``end`` is outside. Windows crossing midnight UTC are ordinary
ranges, not a special case.

Recurring schedules
-------------------
SCHEDULED zones publish hours such as ``"Mon-Fri 1300-2200Z"`` rather than
dated windows. :func:`parse_schedule` reads that text into a
:class:`RecurringSchedule`, and :func:`schedule_is_live` tests a timestamp
against it. Accepted forms:

- days: a single day (``Sat``), a range (``Mon-Fri``, wrapping ``Fri-Mon``),
  a comma list of either (``Mon-Wed,Fri``), or ``Daily``;
- hours: ``HHMM-HHMMZ``; ``2400`` may close a window at midnight;
- hyphen, en dash or em dash between days and between times.

Hours are half-open like :class:`TimeWindow`: ``1300-2200Z`` is live at 1300Z
and cold at 2200Z. If the end is earlier than the start (``2200-0400Z``) the
window runs overnight and belongs to the day it starts on, so Friday's
``2200-0400Z`` is still live at 0300Z Saturday. Hours without ``Z`` are
rejected: local-time schedules need a time zone and DST rules we do not carry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from ..types import Activation, ActivationResult, ActivationState, AirspaceZone

_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")  # datetime.weekday() order
_DASH = "[-–—]"  # hyphen, en dash, em dash
_SCHEDULE_RE = re.compile(
    rf"^\s*(?P<days>\S.*?)\s+(?P<start>\d{{4}})\s*{_DASH}\s*(?P<end>\d{{4}})\s*Z\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RecurringSchedule:
    """A weekly schedule parsed from text like ``"Mon-Fri 1300-2200Z"``."""
    days: frozenset[int]  # datetime.weekday(): Monday is 0
    start_min: int        # minutes after 0000Z, inclusive
    end_min: int          # minutes after 0000Z, exclusive; <= start_min means overnight
    text: str             # the original text, for the analyst-facing basis


def _day(raw: str, text: str) -> int:
    try:
        return _DAYS.index(raw.strip().upper())
    except ValueError:
        raise ValueError(f"unknown day {raw.strip()!r} in schedule {text!r}") from None


def _minutes(raw: str, text: str) -> int:
    hours, minutes = int(raw[:2]), int(raw[2:])
    if minutes > 59 or hours > 24 or (hours == 24 and minutes):
        raise ValueError(f"bad time {raw!r} in schedule {text!r}")
    return hours * 60 + minutes


def parse_schedule(text: str) -> RecurringSchedule:
    """Parse a recurring weekly schedule such as ``"Mon-Fri 1300-2200Z"``.

    Raises ValueError, naming the problem, when ``text`` is not in a form
    described in the module docstring.
    """
    match = _SCHEDULE_RE.match(text)
    if match is None:
        raise ValueError(f"unrecognised schedule {text!r}; expected e.g. 'Mon-Fri 1300-2200Z'")

    days: set[int] = set()
    if match["days"].strip().upper() == "DAILY":
        days.update(range(7))
    else:
        for part in match["days"].split(","):
            ends = re.split(_DASH, part)
            if len(ends) == 1:
                days.add(_day(ends[0], text))
            elif len(ends) == 2:
                first, last = _day(ends[0], text), _day(ends[1], text)
                span = (last - first) % 7
                days.update((first + i) % 7 for i in range(span + 1))
            else:
                raise ValueError(f"bad day range {part.strip()!r} in schedule {text!r}")

    start_min = _minutes(match["start"], text)
    end_min = _minutes(match["end"], text)
    if start_min == end_min:
        raise ValueError(f"schedule {text!r} opens and closes at the same time")
    if start_min == 24 * 60:
        raise ValueError(f"schedule {text!r} cannot open at 2400")

    return RecurringSchedule(frozenset(days), start_min, end_min, text.strip())


def schedule_is_live(schedule: RecurringSchedule, ts: datetime) -> bool:
    """True when tz-aware ``ts`` falls inside ``schedule``.

    Raises ValueError when ``ts`` is naive.
    """
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError(f"schedule_is_live needs a tz-aware UTC timestamp, got naive {ts!r}")
    ts = ts.astimezone(UTC)
    now_min = ts.hour * 60 + ts.minute
    today, yesterday = ts.weekday(), (ts.weekday() - 1) % 7

    if schedule.start_min < schedule.end_min:
        return today in schedule.days and schedule.start_min <= now_min < schedule.end_min
    # Overnight: today's window has opened, or yesterday's has not yet closed.
    return (today in schedule.days and now_min >= schedule.start_min) or (
        yesterday in schedule.days and now_min < schedule.end_min
    )


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

    # 4. SCHEDULED with recurring hours: the schedule decides. Text we cannot
    #    read is UNKNOWN, not a crash and not a guess.
    if zone.activation is Activation.SCHEDULED and zone.schedule:
        try:
            schedule = parse_schedule(zone.schedule)
        except ValueError as err:
            return ActivationResult(ActivationState.UNKNOWN, zone.zone_id, str(err))
        if schedule_is_live(schedule, ts):
            return ActivationResult(
                ActivationState.ACTIVE,
                zone.zone_id,
                f"{zone.zone_type.value} schedule {schedule.text}",
            )
        return ActivationResult(
            ActivationState.INACTIVE,
            zone.zone_id,
            f"outside published schedule {schedule.text}",
        )

    # 5. WINDOW or SCHEDULED with no windows listed: no schedule is not the
    #    same as "off", so report UNKNOWN rather than INACTIVE.
    if not zone.active_windows:
        return ActivationResult(
            ActivationState.UNKNOWN,
            zone.zone_id,
            f"{zone.activation.value} zone with no published windows",
        )

    # 6. Live if ts falls inside any window. Half-open: start <= ts < end.
    for window in zone.active_windows:
        if window.start <= ts < window.end:
            basis = (
                f"{zone.zone_type.value} window "
                f"{window.start:%H%M}Z-{window.end:%H%M}Z"
            )
            return ActivationResult(ActivationState.ACTIVE, zone.zone_id, basis)

    # 7. Windows exist but none covers ts: the zone was cold.
    return ActivationResult(
        ActivationState.INACTIVE,
        zone.zone_id,
        f"outside all {len(zone.active_windows)} published window(s)",
    )