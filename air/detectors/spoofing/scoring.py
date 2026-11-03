"""Scoring: how weird is it, and how sure are we?

Two separate numbers, and conflating them is the easiest mistake in the
detector.

``anomaly_score`` is *how far past the limit* the value went. ``confidence_for``
is *how much the measurement can be trusted*. A reading of 20,000 kt built on
two sparse reports is high score, low confidence -- and the right response is
silence, not an alarm.
"""

from __future__ import annotations

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.quality import fix_quality_factor
from air.detectors.spoofing.records import SpoofingEvent
from air.detectors.spoofing.severity_rules import severity_weight
from contracts import SeverityLevel

# The fixed level-per-gate table that used to live here is gone: severity is
# now the gate's weight times how far past its limit the hit went. Its
# judgement was not thrown away -- each gate's standing was carried across
# into SEVERITY_WEIGHTS, so nothing was silently re-rated.

# What a gate with no number scores. It fired, so it is not zero; we simply
# cannot say how far past the line it went.
UNMEASURED_SCORE = 0.6


def anomaly_score(
    measured: float | None, threshold: float | None, margin: float | None = None
) -> float:
    """How far past the limit a value went, from 0.0 to 1.0.

    Exactly at the threshold the score is 0.5; a full margin beyond it
    reaches 1.0; anything further saturates there. An aircraft at 1,001 kt
    is barely over the line and one at 21,000 kt is wildly over, and this is
    the number that distinguishes them.

    Shape copied from ``altitude_confidence`` in the reference detector.

    Returns ``UNMEASURED_SCORE`` when there is nothing to measure.
    ``identity_drift_v1`` is the one gate in that position: it is a yes or
    no, with no quantity attached.
    """
    if measured is None or threshold is None:
        return UNMEASURED_SCORE

    limit = abs(float(threshold))
    value = abs(float(measured))
    span = abs(float(margin)) if margin else limit

    if span <= 0:
        return 1.0 if value > limit else 0.5

    overshoot = value - limit
    if overshoot <= 0:
        return 0.5
    return round(min(1.0, 0.5 + 0.5 * min(overshoot, span) / span), 3)


def score_for(event: SpoofingEvent, cfg: SpoofingConfig) -> float:
    """The anomaly score for an event, under this config.

    Both callers must use this rather than calling ``anomaly_score``
    directly. The detector scores an event to decide whether to abstain, and
    the emitter scores it again to record on the alert; if those two derived
    the margin differently, an alert could carry a score that contradicts the
    decision to raise it.
    """
    margin = None
    if event.threshold:
        margin = abs(event.threshold) * cfg.score_margin_frac
    return anomaly_score(event.measured, event.threshold, margin)


def confidence_for(event: SpoofingEvent, cfg: SpoofingConfig) -> float:
    """How much the measurement behind an event can be trusted, 0.0 to 1.0.

    This asks nothing about how extreme the value is -- only whether the
    evidence was good enough to produce a number worth believing. It drops
    when:

    * the two reports were very close together, where timestamp error
      dominates the arithmetic
    * the segment held too few observations to establish a pattern
    * fields the rule needed were absent

    Deliberately conservative. A detector that is loudly wrong is worse than
    one that stays quiet, because an analyst who gets bad alerts stops
    reading them.
    """
    confidence = 1.0

    features = event.features
    if features:
        shortest_dt = min(f.dt_s for f in features)
        if shortest_dt < cfg.min_dt_s * 2:
            confidence -= 0.3
        elif shortest_dt < cfg.min_dt_s * 4:
            confidence -= 0.1
    else:
        # No feature records attached: nothing to inspect.
        confidence -= 0.3

    observations = event.details.get("observation_count")
    if isinstance(observations, int) and observations < cfg.min_segment_observations:
        confidence -= 0.3

    if event.measured is None or event.threshold is None:
        confidence -= 0.2

    # Finally, what the aircraft says about its own fix. Most of these rules
    # are arithmetic on two positions, so a disagreement computed from a fix
    # the aircraft itself calls unreliable is a weaker finding than the same
    # disagreement from a good one. Scaling rather than subtracting keeps the
    # deductions above meaning what they say; a feed that omits NIC and NACp
    # returns 1.0 and is unaffected.
    if features:
        confidence *= min(fix_quality_factor(f) for f in features)

    return round(max(0.0, min(1.0, confidence)), 3)


def severity_for(
    gate: str, score: float | None = None, cfg: SpoofingConfig | None = None
) -> SeverityLevel:
    """How loud the alarm should be: what kind of finding, and how far over.

    Two things decide it. ``severity_weight`` says how much this kind of
    finding matters at all -- a teleport is near-certain evidence of
    spoofing, a turn-rate hit much weaker. ``anomaly_score`` says how far
    past the limit this particular one went. Multiplying them means a weak
    rule firing marginally cannot reach the loudness of a strong rule
    firing hard.

    This replaced a fixed level per rule, under which every hit on a gate
    arrived identical: one real run emitted 156 HIGH out of 286 alerts,
    which tells a reader nothing and teaches them to ignore the field.

    Called without a score it falls back to ``UNMEASURED_SCORE``, the value
    ``anomaly_score`` itself returns for a gate with no quantity attached.
    An unknown gate takes the default weight rather than raising -- a new
    rule must not be able to crash the pipeline on its first run.
    """
    if cfg is None:
        cfg = SpoofingConfig()
    if score is None:
        score = UNMEASURED_SCORE

    combined = severity_weight(gate) * score
    if combined >= cfg.severity_high_at:
        return SeverityLevel.HIGH
    if combined >= cfg.severity_medium_at:
        return SeverityLevel.MEDIUM
    return SeverityLevel.LOW


def should_abstain(score: float, confidence: float, cfg: SpoofingConfig) -> bool:
    """Whether to stay quiet instead of raising an alert.

    Confidence below the floor means the evidence was too thin to judge, no
    matter how extreme the reading. "This aircraft did 20,000 kt, but I had
    two messages to go on" is exactly the case this exists for.

    The repo rule is abstain rather than guess: a missed detection costs
    less than a false alarm, because false alarms destroy trust in every
    later one.
    """
    if confidence < cfg.min_confidence:
        return True
    return False


__all__ = [
    "anomaly_score",
    "score_for",
    "confidence_for",
    "severity_for",
    "should_abstain",
    "UNMEASURED_SCORE",
]
