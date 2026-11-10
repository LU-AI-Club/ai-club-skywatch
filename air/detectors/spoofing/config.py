"""Every limit the spoofing detector uses, in one place.

No rule may hard-code a number. They all read from here, which is what lets
the evaluation lane sweep a threshold across many values without touching
anyone's code, and what lets each alert record the exact limits that produced
it.

The values below are baseline v0: defensible starting points, not final
answers. Section 4 of the design doc explains each one.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class SpoofingConfig:
    """Thresholds for the physics and identity rules."""

    # --- physics ---------------------------------------------------------
    teleport_kt: float = 1000.0
    """No aircraft exceeds this over the ground.

    Airliners genuinely reach 750-800 kt in a strong jet stream, and real
    fabricated positions imply thousands to tens of thousands. 1000 clears
    honest flight entirely while still catching every fake.
    """

    turn_rate_dps: float = 10.0
    """A standard rate turn is 3 deg/s. 10 is aerobatic and unsustainable."""

    turn_rate_min_speed_kt: float = 150.0
    """Below this reported ground speed, turn rate is not measured at all.

    Track is the direction of travel, and an aircraft barely moving has
    almost none: a taxiing aircraft, a tug, or a parked transmitter swings
    its reported heading freely without turning in any sense the rule means.
    This was our largest single source of false alerts -- 156 of 312, median
    reported speed 55 kt, 93% of them under 150 kt.

    The limit is a speed at which track becomes meaningful, not an aircraft
    class. A genuinely impossible turn happens at flying speed, which is why
    the guard fixture turns at 450 kt.
    """

    speed_delta_kt: float = 50.0
    """How far claimed and derived ground speed may disagree..."""

    speed_delta_frac: float = 0.30
    """...or this fraction of the reported speed, whichever is larger.

    A fixed margin alone is wrong for both a 90 kt Cessna and a 500 kt jet.
    """

    position_error_m: float = 30.0
    """How far off a single reported position may be, in metres.

    Implied speed is distance over time, so position error becomes phantom
    speed, and the shorter the gap the larger it gets: 30 m of error at each
    end over 0.55 s reads as 212 kt, on an aircraft flying perfectly
    steadily. 30 m is the NACp 9 bound (95% containment), typical of
    GPS-quality ADS-B. Without accounting for it, 80% of speed-delta alerts
    on the real file were pairs under one second apart.
    """

    timing_error_s: float = 0.25
    """How far a report's timestamp may sit from the fix it carries.

    The timestamp is when we received the message; the position inside it
    was measured slightly earlier, and by a varying amount. Implied speed
    divides distance by the gap between timestamps, so a timing slip is a
    speed error of ``reported_speed * timing_error_s / dt_s``: large at
    short gaps, negligible at long ones, and proportional to how fast the
    aircraft is going rather than to any distance.

    This is a different error from ``position_error_m`` and has to be
    allowed for separately. The evidence is in the raw feed: one aircraft at
    a steady 390 kt advances 0.00418, 0.00664, 0.00584 and 0.00418 degrees
    of longitude over gaps of 2.02, 3.14, 1.91 and 2.97 s. No single step
    gives 390 kt; all four together do exactly. Across the hour the ratio of
    implied to reported speed has a median of 1.00 at every gap size, while
    its 5th-95th percentile spread tightens from 0.82-1.20 under a second to
    0.99-1.01 past ten -- the signature of a time error, not a lie.

    0.25 s is near the 99th percentile of that spread. It is deliberately
    not generous enough to excuse a real lie: a 4.5x speed contradiction at
    the feed's fastest cadence still fires.
    """

    vrate_delta_fpm: float = 2000.0
    """Above barometric noise and sensor lag; a normal climb is 1500-2500."""

    vrate_max_plausible_fpm: float = 6000.0
    """A reported climb rate beyond this is a corrupt field, not a claim.

    Nothing in this traffic climbs at 6,000 fpm: across 279,725 messages the
    99.9th percentile is 4,544 fpm, and only 41 exceed 6,000 -- values like
    +18,176 and +32,192 fpm, broadcast by aircraft holding altitude exactly.
    Those are decode errors in the rate field, the same class of corruption
    as a garbled callsign.

    A number that cannot be true is not evidence that the aircraft lied; it
    is evidence we did not receive the field. Comparing it against the
    altitude can only manufacture a disagreement, so the rule abstains. See
    ``flag_vrate_delta``.
    """

    altitude_quantum_min_samples: int = 4
    """How many altitude changes a segment must show before we read its step.

    The step is inferred as the common divisor of a segment's altitude
    changes. With one or two changes a coincidence is as likely as a
    measurement -- two steps of 100 ft prove nothing about an aircraft that
    usually moves in 25s -- so below this count we fall back to
    ``altitude_quantum_ft``.
    """

    altitude_quantum_max_ft: float = 100.0
    """The coarsest altitude step we will believe is rounding.

    100 ft is the Mode C granularity still in use alongside 25 ft reporting.
    A larger common divisor means we are reading a climb rather than a
    rounding step, and accepting it would hand the rule an allowance wide
    enough to hide a real lie, so it is rejected and the default applies.
    """

    altitude_quantum_ft: float = 25.0
    """The step size altitude is reported in, when the aircraft has not shown us.

    Most of this feed rounds altitude to 25 ft. A level aircraft therefore
    appears to jump a whole step at a time, and over a short gap that implies
    a large climb rate purely as an artefact: 25 ft in 0.55 s reads as
    2,727 fpm. Without accounting for it, 96% of all alerts on the real file
    were level aircraft tripping the vertical-rate rule.

    This is only the fallback. Where a segment moves enough to show its own
    step, the rule uses that instead -- 31 aircraft in the same hour report
    in 100 ft steps, and 25 ft is badly wrong for them.
    """

    nic_floor: int = 1
    """Navigation integrity at or below this reads as 'the aircraft does not
    trust its own position'."""

    nic_min_duration_s: float = 30.0
    """How long integrity must stay down before it is a finding. Brief dips
    are ordinary equipment behaviour."""

    # --- identity --------------------------------------------------------
    pingpong_reversals: int = 3
    """Impossible hops that reverse direction, in a row, before it reads as
    two transmitters sharing one identity rather than one bad position."""

    reachable_margin_frac: float = 0.10
    """Slack added to the reachable-distance circle, covering wind and
    position error, before a reappearance counts as impossible."""

    # --- pipeline --------------------------------------------------------
    max_gap_s: float = 60.0
    """Silence longer than this splits a track. Never compute across it."""

    min_dt_s: float = 0.5
    """Pairs closer together than this are not scored: at very short gaps,
    timestamp error dominates and implied speed becomes meaningless."""

    # --- scoring ---------------------------------------------------------
    score_margin_frac: float = 1.0
    """How far past a threshold counts as fully anomalous. 1.0 means twice
    the limit scores 1.0."""

    episode_gap_s: float = 60.0
    """How long one aircraft must go quiet before a rule's hits count twice.

    A rule testing consecutive pairs fires once per pair, so one stretch of
    behaviour arrives as many identical findings: on a real hour one
    aircraft produced twelve climb-rate alerts for a single episode. Hits of
    the same rule on the same aircraft closer together than this are
    reported as one, which is the difference between "twelve aircraft
    misbehaved" and "one aircraft misbehaved twelve times".

    Matches ``max_gap_s``, since that is already where the detector decides
    a track has been interrupted.
    """

    severity_high_at: float = 0.6
    """Combined weight-times-score at or above which an alert reads HIGH."""

    severity_medium_at: float = 0.35
    """...and at or above which it reads MEDIUM. Below this it is LOW.

    Severity used to be a fixed lookup per rule, so every teleport and every
    turn-rate wobble arrived at the same loudness: one real run emitted 156
    HIGH out of 286, which tells a reader nothing. It is now how much the
    kind of finding matters (``severity_weight``) multiplied by how far past
    the limit this one went (``anomaly_score``), so a rule that fires on
    something marginal no longer shouts.
    """

    min_confidence: float = 0.35
    """Below this, abstain rather than alert. A wild reading built on thin
    evidence is not worth waking anyone for."""

    min_segment_observations: int = 3
    """A segment shorter than this is treated as thin evidence."""

    def __post_init__(self) -> None:
        for name in ("teleport_kt", "turn_rate_dps", "speed_delta_kt", "vrate_delta_fpm"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than 0")
        if not 0.0 < self.speed_delta_frac < 1.0:
            raise ValueError("speed_delta_frac must be between 0 and 1")
        if self.position_error_m < 0:
            raise ValueError("position_error_m must not be negative")
        if not 0.0 <= self.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0.0 and 1.0")
        if self.max_gap_s <= self.min_dt_s:
            raise ValueError("max_gap_s must be greater than min_dt_s")

    def to_parameters(self) -> dict[str, Any]:
        """Every setting as a flat dict, recorded on each Detection.

        An alert is only interpretable next to the limits that produced it.
        Change a threshold next week and yesterday's detections must still
        say what they were measured against.

        Note there is a second ``to_parameters`` in this project, on
        ``SpoofingEvent``. Different object, different file, same name.
        """
        return {f.name: getattr(self, f.name) for f in fields(self)}


__all__ = ["SpoofingConfig"]
