"""How good the aircraft says its own position fix was.

Confidence currently reflects only how much evidence we gathered -- how far
apart the reports were, how many of them there were. It ignores a statement
the aircraft makes about itself in every message: NIC and NACp, its own
assessment of how much its position can be trusted.

That matters because most of our rules are arithmetic on two positions. A
disagreement computed from a fix the aircraft itself calls unreliable is a
weaker finding than the same disagreement computed from a good one, and the
alert should say so rather than presenting both as equally certain.

This is not a rule and never fires. It returns a multiplier for confidence.
"""

from __future__ import annotations

from air.detectors.spoofing.records import SpoofingFeatureRecord

__all__ = ["fix_quality_factor", "NIC_BEST", "NACP_BEST", "FLOOR"]

# The top of each scale in DO-260B. NIC 11 is a containment radius under
# 7.5 m; NACp 11 is a 95% position error under 3 m.
NIC_BEST = 11
NACP_BEST = 11

# No fix is poor enough to make a finding worthless. A gross teleport is
# still a teleport when the aircraft admits its GPS is bad, so the factor
# never falls below this.
FLOOR = 0.3


def _scaled(value: int | None, best: int) -> float | None:
    """One reported integrity value as 0.0 to 1.0, or None if not stated.

    Values outside the published range are clamped rather than rejected:
    a malformed field should weaken the alert, not crash the detector.
    """
    if value is None:
        return None
    return max(0.0, min(1.0, value / best))


def fix_quality_factor(record: SpoofingFeatureRecord) -> float:
    """A 0.0-1.0 multiplier for how much to trust this record's positions.

    1.0 means the aircraft reports the best possible fix on both rows. Lower
    means it admits its own position is unreliable, and the finding built on
    that position is correspondingly weaker.

    All four values are considered -- NIC and NACp, on the previous row and
    the current one -- because the measurement spans both reports, and the
    worse of the two bounds the pair. The lowest value present therefore
    decides the result: a good fix followed by a bad one is a bad pair.

    Returns 1.0 when nothing was reported. Silence is not an admission of a
    poor fix, and penalising it would quietly down-rank every aircraft on a
    feed that happens not to carry these fields.
    """
    stated = [
        scaled
        for scaled in (
            _scaled(record.prev_nic, NIC_BEST),
            _scaled(record.nic, NIC_BEST),
            _scaled(record.prev_nacp, NACP_BEST),
            _scaled(record.nacp, NACP_BEST),
        )
        if scaled is not None
    ]
    if not stated:
        return 1.0

    return round(max(FLOOR, min(stated)), 3)
