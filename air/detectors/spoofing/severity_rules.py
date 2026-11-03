"""Per-gate severity weights for spoofing detection.

Severity should reflect how much a *kind* of finding matters, not just how
far past its limit one went. A teleport is near-certain evidence of
spoofing; a turn-rate hit is weaker evidence even when the number is large.

Severity used to be a fixed level per rule, so every hit on a gate arrived
identically loud: one real run emitted 156 HIGH out of 286 alerts, which
tells a reader nothing and teaches them to ignore the field. ``severity_for``
multiplies the weight here by the anomaly score to get the level.

These are weights on evidence, not on how alarming the words sound. They say
how readily something other than spoofing explains the finding.
"""

DEFAULT_WEIGHT = 0.5

# Weight is 0.0 to 1.0: how much this kind of finding matters.
SEVERITY_WEIGHTS: dict[str, float] = {
    # One address cannot be in two places at once, and no aircraft crosses
    # hundreds of miles in seconds. Almost nothing innocent produces these.
    "teleport_v1": 1.0,
    "coexistence_v1": 0.95,
    # Below the terrain it is flying over, or alternating between two
    # positions. Both are impossible rather than merely improbable; they sit
    # just under the two above because each leans on data we supply (a
    # terrain model, a reachability margin) rather than on geometry alone.
    "subterrain_v1": 0.9,
    "pingpong_v1": 0.85,
    # An address that contradicts its registration, or belongs to another
    # aircraft. Strong evidence, but reference data goes stale.
    "registry_mismatch_v1": 0.8,
    "impersonation_v1": 0.8,
    # Came back from a silence further away than it could have flown. Real,
    # but the longer the gap the more the margin is doing the work.
    "reappear_v1": 0.55,
    # The aircraft's claim contradicts its own positions. Our highest-volume
    # rules, and the two most exposed to measurement error: position error,
    # timestamp slip and altitude rounding all push these the wrong way, and
    # each is allowed for by an estimate rather than known exactly. Mid-scale
    # on purpose -- they need the score to be high before they are.
    "speed_delta_v1": 0.5,
    "vrate_delta_v1": 0.5,
    # Recalibrated when flag_turn_rate gained its minimum-speed gate.
    # 0.2 was set while the rule fired on taxiing aircraft and roughly half
    # its alerts were noise, which capped it below MEDIUM at any score. It
    # now abstains below flying speed, so a hit means an aircraft at cruise
    # reporting a turn no airframe can fly. That is real evidence, though
    # heading is noisier than position, which keeps it under the two above.
    "turn_rate_v1": 0.7,
    # A callsign change is suggestive and little more. Garbled receptions
    # are filtered out before this rule sees them.
    "identity_drift_v1": 0.3,
    # The aircraft reporting that it does not trust its own position. That
    # is a reason to doubt everything else it says, and jamming or a failing
    # receiver explains it at least as readily as spoofing does.
    "nic_floor_v1": 0.3,
}


def severity_weight(gate: str) -> float:
    """Return 0.0 to 1.0 for how much this kind of finding matters.

    gate: the rule name, e.g. "teleport_v1", "turn_rate_v1".
    Unknown gates return DEFAULT_WEIGHT (0.5), so a new rule lands in the
    middle of the scale rather than silently at the bottom of it.
    """
    return SEVERITY_WEIGHTS.get(gate, DEFAULT_WEIGHT)
