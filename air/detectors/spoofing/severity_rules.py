"""Severity currently just tracks the score. On the last real run we emitted
156 HIGH out of 286, which is useless to anyone reading alerts.
 
A teleport and a turn-rate wobble should not be the same severity at the
same score."""

"""Per-gate severity weights for spoofing detection.

Severity should reflect how much a *kind* of finding matters, not just its score.
A teleport is near-certain evidence of spoofing; a turn-rate wobble is often noise.
"""

DEFAULT_WEIGHT = 0.5

# Weight is 0.0 to 1.0: how much this kind of finding matters.
SEVERITY_WEIGHTS: dict[str, float] = {
    "teleport_v1": 1.0,
    "coexistence_v1": 0.95,
    "registry_mismatch_v1": 0.8,
    "impersonation_v1": 0.8,
    "identity_drift_v1": 0.3,
    "turn_rate_v1": 0.2,
}


def severity_weight(gate: str) -> float:
    """Return 0.0 to 1.0 for how much this kind of finding matters.

    gate: the rule name, e.g. "teleport_v1", "turn_rate_v1".
    Unknown gates return DEFAULT_WEIGHT (0.5).
    """
    return SEVERITY_WEIGHTS.get(gate, DEFAULT_WEIGHT)