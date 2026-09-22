"""Rule functions: look at one feature record (or segment), decide
whether it's worth flagging.

Every flag_* function takes the thing to check plus a SpoofingConfig,
and returns either a short reason string (the rule name) or None.
None always means "this rule did not fire" -- never "I don't know."
Style follows flag_altitude in air/detectors/_example_altitude/detector.py.

NOTE ON FIELD NAMES: the exact attribute names on SpoofingFeatureRecord
belong to Christopher's records.py / build_pair_features. The ones used
below (implied_speed_kt, turn_rate_deg_s, claimed_speed_kt,
implied_vrate_fpm, etc.) are my best read of the worksheet's function
table -- confirm them against records.py before opening a PR, and
rename here if they don't match.
"""

from __future__ import annotations

from typing import Iterable, Optional

from air.detectors.spoofing.config import SpoofingConfig


def flag_teleport(record, config: SpoofingConfig) -> Optional[str]:
    """Flag a pair whose implied ground speed is impossible.

    Args:
        record: A SpoofingFeatureRecord (or anything with an
            `implied_speed_kt` attribute) built from two consecutive
            messages from the same aircraft.
        config: Limits to check against.

    Returns:
        "TELEPORT" if implied_speed_kt is over config.teleport_kt,
        otherwise None.
    """
    if record.implied_speed_kt > config.teleport_kt:
        return "TELEPORT"
    return None


def flag_turn_rate(record, config: SpoofingConfig) -> Optional[str]:
    """Flag a pair that turned faster than physically possible.

    Args:
        record: A SpoofingFeatureRecord with a `turn_rate_deg_s`
            attribute (degrees per second; see heading_delta_deg for
            how the underlying turn is measured).
        config: Limits to check against.

    Returns:
        "TURN_RATE" if turn_rate_deg_s is over config.turn_rate_deg_s,
        otherwise None.
    """
    if abs(record.turn_rate_deg_s) > config.turn_rate_deg_s:
        return "TURN_RATE"
    return None


def flag_speed_delta(record, config: SpoofingConfig) -> Optional[str]:
    """Flag a pair where claimed and calculated speed disagree.

    "Claimed" is what the aircraft radioed as its own ground speed;
    "calculated" is what we work out ourselves from position and time
    (implied_speed_kt). Fires only when the gap is big in both
    absolute *and* relative terms, so a slow plane with a tiny
    absolute gap doesn't trip it, and a fast plane with a tiny
    percentage gap doesn't either.

    Args:
        record: A SpoofingFeatureRecord with `claimed_speed_kt` and
            `implied_speed_kt` attributes.
        config: Limits to check against.

    Returns:
        "SPEED_DELTA" if the two speeds disagree by more than both
        config.speed_delta_kt knots and config.speed_delta_pct of the
        claimed speed, otherwise None.
    """
    delta = abs(record.claimed_speed_kt - record.implied_speed_kt)
    pct_limit = config.speed_delta_pct * abs(record.claimed_speed_kt)
    if delta > config.speed_delta_kt and delta > pct_limit:
        return "SPEED_DELTA"
    return None


def flag_vrate_delta(record, config: SpoofingConfig) -> Optional[str]:
    """Flag a pair where claimed and calculated climb rate disagree.

    Same idea as flag_speed_delta, but vertical: what the aircraft
    radioed (`claimed_vrate_fpm`) versus what the change in altitude
    over time actually works out to (`implied_vrate_fpm`).

    Args:
        record: A SpoofingFeatureRecord with `claimed_vrate_fpm` and
            `implied_vrate_fpm` attributes.
        config: Limits to check against.

    Returns:
        "VRATE_DELTA" if the two climb rates disagree by more than
        config.vrate_delta_fpm, otherwise None.
    """
    delta = abs(record.claimed_vrate_fpm - record.implied_vrate_fpm)
    if delta > config.vrate_delta_fpm:
        return "VRATE_DELTA"
    return None


def flag_nic_floor(segment: Iterable, config: SpoofingConfig) -> Optional[str]:
    """Flag a segment whose GPS-trust value is stuck low too long.

    NIC (Navigation Integrity Category) is the aircraft's own claim of
    how much to trust its position. A brief dip to 0 or 1 is normal
    (a moment of poor satellite coverage); sitting there for a long
    stretch is a sign the position feed itself is being spoofed.

    Args:
        segment: One aircraft's observations for a single unbroken
            stretch (as produced by split_segments), each with `nic`
            and `timestamp` attributes, in time order.
        config: Limits to check against.

    Returns:
        "NIC_FLOOR" if the observations spend config.nic_floor_s
        seconds or more continuously at nic 0 or 1, otherwise None.
    """
    run_start = None
    for obs in segment:
        if obs.nic <= 1:
            if run_start is None:
                run_start = obs.timestamp
            elif obs.timestamp - run_start >= config.nic_floor_s:
                return "NIC_FLOOR"
        else:
            run_start = None
    return None
