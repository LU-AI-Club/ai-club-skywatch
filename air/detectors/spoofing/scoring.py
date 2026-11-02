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
from air.detectors.spoofing.records import SpoofingEvent
from contracts import SeverityLevel

# Physics limits sit beyond what is possible, so a hit is a finding rather
# than a judgement call. Residuals have innocent explanations. A single soft
# indicator is weaker still.
_SEVERITY_BY_GATE: dict[str, SeverityLevel] = {
    "teleport_v1": SeverityLevel.HIGH,
    "turn_rate_v1": SeverityLevel.HIGH,
    "subterrain_v1": SeverityLevel.HIGH,
    "coexistence_v1": SeverityLevel.HIGH,
    "pingpong_v1": SeverityLevel.HIGH,
    "reappear_v1": SeverityLevel.MEDIUM,
    "speed_delta_v1": SeverityLevel.MEDIUM,
    "vrate_delta_v1": SeverityLevel.MEDIUM,
    "registry_mismatch_v1": SeverityLevel.MEDIUM,
    "nic_floor_v1": SeverityLevel.LOW,
    "identity_drift_v1": SeverityLevel.LOW,
}

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

    return round(max(0.0, min(1.0, confidence)), 3)


def severity_for(gate: str) -> SeverityLevel:
    """How loud the alarm should be, from which rule fired.

    Physics violations are HIGH: their limits sit beyond the possible, so a
    hit means something is genuinely wrong. Residuals are MEDIUM, since
    claimed and derived values disagreeing has innocent explanations. A
    single soft indicator is LOW.

    An unknown gate is LOW rather than an error -- a new rule should not be
    able to crash the pipeline on its first run.
    """
    return _SEVERITY_BY_GATE.get(gate, SeverityLevel.LOW)


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
