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

from datetime import datetime

from ..types import Activation, ActivationResult, ActivationState, AirspaceZone


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
    if not zone.active_windows:
        return ActivationResult(
            ActivationState.UNKNOWN,
            zone.zone_id,
            f"{zone.activation.value} zone with no published windows",
        )

    # 5. Live if ts falls inside any window. Half-open: start <= ts < end.
    for window in zone.active_windows:
        if window.start <= ts < window.end:
            basis = (
                f"{zone.zone_type.value} window "
                f"{window.start:%H%M}Z-{window.end:%H%M}Z"
            )
            return ActivationResult(ActivationState.ACTIVE, zone.zone_id, basis)

    # 6. Windows exist but none covers ts: the zone was cold.
    return ActivationResult(
        ActivationState.INACTIVE,
        zone.zone_id,
        f"outside all {len(zone.active_windows)} published window(s)",
    )