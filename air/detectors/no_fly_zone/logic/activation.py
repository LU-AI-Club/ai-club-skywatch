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

from ..types import Activation, ActivationResult, ActivationState, AirspaceZone, TimeWindow


def is_active(zone: AirspaceZone, ts: datetime) -> ActivationResult:
    """Decide whether ``zone`` was live at ``ts``.

    Raises:
        ValueError: ``ts`` is naive.
    """
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("is_active needs a tz-aware UTC timestamp, got a naive datetime")

    def result(state: ActivationState, basis: str) -> ActivationResult:
        return ActivationResult(state=state, zone_id=zone.zone_id, basis=basis)

    if zone.activation is Activation.ALWAYS:
        return result(ActivationState.ACTIVE, "always active")
    if zone.activation is Activation.NOTAM:
        return result(
            ActivationState.UNKNOWN,
            "activated by NOTAM, and no NOTAM data was available to check",
        )

    label = "TFR window" if zone.activation is Activation.WINDOW else "scheduled window"
    if not zone.active_windows:
        return result(
            ActivationState.UNKNOWN,
            f"{zone.activation.value.lower()} activation, but no windows were published to check",
        )
    for window in zone.active_windows:
        if window.start <= ts < window.end:
            return result(ActivationState.ACTIVE, f"{label} {_span(window)}")
    return result(
        ActivationState.INACTIVE,
        f"outside every published window ({', '.join(_span(w) for w in zone.active_windows)})",
    )


def _span(window: TimeWindow) -> str:
    return f"{window.start:%Y-%m-%dT%H%MZ}-{window.end:%Y-%m-%dT%H%MZ}"
