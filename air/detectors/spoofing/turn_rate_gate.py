"""Measurability gate for the turn-rate rule.

Turn rate is the detector's largest noise source: 156 of 286 alerts, median
reported speed on those alerts 55 kt, 93% of them under 150 kt. That is not
spoofing, it is geometry. ``turn_rate_dps`` comes from the change in reported
track, and track is the direction of the aircraft's velocity vector. The slower
the aircraft, the less velocity there is to take a direction from, so a small
absolute movement swings the reported heading a long way. An aircraft taxiing
at 10 kt can show 90 deg/s honestly; a parked one with a live transponder can
show anything at all.

So the problem is not that slow aircraft turn faster than the threshold
allows. It is that below some speed the measurement does not mean anything,
and a rule firing on a number that means nothing is noise whatever the
threshold is set to. Raising ``turn_rate_dps`` would trade this noise for
missed real turns; gating on measurability drops it without touching the
sensitivity of the rule where it does work.

This module answers only that question -- *can* this record's turn rate be
trusted -- and deliberately not *is* the turn too sharp, which stays in
``physics.flag_turn_rate``. Keeping them apart means the threshold sweep still
sweeps one number, and an abstention is distinguishable from a pass.

The gate reads its limit with ``getattr(cfg, "turn_rate_min_speed_kt", 150.0)``
so it works before that setting lands in ``SpoofingConfig``. Once the field
exists the fallback stops being used, and nothing here needs to change.

Not gated on here:

* ``dt_s`` -- ``flag_turn_rate`` already abstains below ``cfg.min_dt_s``.
* ``nic`` / ``nacp`` -- track comes from the velocity message, not the
  position fix, so position integrity says nothing about it. ``flag_turn_rate``
  notes the same thing.
"""

from __future__ import annotations

import math

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.records import SpoofingFeatureRecord

DEFAULT_TURN_RATE_MIN_SPEED_KT = 150.0
"""Below this reported ground speed a turn rate is not a measurement.

150 kt sits above the 93rd percentile of the speeds seen on turn-rate alerts
and above circuit and approach speeds for the light traffic that produced
them, while staying well under any airliner's cruise. It is a starting point
chosen from the alert distribution, not a derived constant -- the right way to
settle it is a sweep against the fixture corpus.
"""


def turn_rate_min_speed_kt(cfg: SpoofingConfig) -> float:
    """The speed floor this config asks for, in knots.

    Resolved through ``getattr`` so the gate predates the config field. A
    configured ``None`` is read as "no floor", which disables the gate rather
    than crashing on a comparison against ``None``.
    """
    limit = getattr(cfg, "turn_rate_min_speed_kt", DEFAULT_TURN_RATE_MIN_SPEED_KT)
    if limit is None:
        return 0.0
    return float(limit)


def is_turn_rate_measurable(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> bool:
    """Whether this record's turn rate is worth testing at all.

    Parameters
    ----------
    record:
        The pair record whose ``turn_rate_dps`` is about to be judged.
    cfg:
        Supplies the speed floor via ``turn_rate_min_speed_kt``.

    Returns
    -------
    bool
        ``False`` when the turn rate cannot be trusted and the rule should
        abstain; ``True`` otherwise.

    ``False`` when:

    * ``reported_speed_kt`` is ``None`` -- the aircraft did not say how fast it
      was going, so there is nothing to establish measurability from. Abstain
      rather than assume it was fast enough.
    * ``reported_speed_kt`` is not a finite number -- a ``NaN`` from a bad
      decode compares ``False`` against everything, so without this it would
      slip through every threshold check and read as measurable.
    * ``reported_speed_kt`` is below the floor -- heading is noise-dominated
      down there.

    The comparison is strict, so a record exactly at the floor is measurable:
    the floor is the lowest speed still trusted, not the first one rejected.

    The reported speed is used rather than ``implied_speed_kt`` on purpose.
    What makes the heading noisy is the aircraft's own velocity, which is what
    the velocity message reports and what the track is derived from. Implied
    speed is a position-difference artefact and is exactly the quantity a
    fabricated position corrupts, so gating on it would let a spoof widen its
    own gate.
    """
    speed = record.reported_speed_kt
    if speed is None:
        return False
    speed = float(speed)
    if not math.isfinite(speed):
        return False
    return speed >= turn_rate_min_speed_kt(cfg)


__all__ = [
    "is_turn_rate_measurable",
    "turn_rate_min_speed_kt",
    "DEFAULT_TURN_RATE_MIN_SPEED_KT",
]
