"""Team limits and settings for the spoofing detector.

Every numeric threshold used by the rule functions in physics.py lives
here, in one place, so nobody has to go hunting for a magic number
buried in the middle of a function.
"""

from dataclasses import dataclass, asdict


@dataclass
class SpoofingConfig:
    """Every limit the spoofing rules check against.

    Attributes:
        teleport_kt: Implied ground speed above this is physically
            impossible. Default 1000 kt.
        turn_rate_deg_s: Turn rate above this is impossible in level
            flight. Default 10 deg/s.
        speed_delta_kt: Absolute knots the claimed and calculated
            speed are allowed to disagree by before it's suspicious.
            Default 50 kt.
        speed_delta_pct: Fraction (0-1) the claimed and calculated
            speed are allowed to disagree by, relative to the claimed
            speed, before it's suspicious. Default 0.30 (30%).
        vrate_delta_fpm: Feet-per-minute the claimed and calculated
            climb rate are allowed to disagree by. Default 2000 fpm.
        nic_floor_s: Seconds GPS-trust (NIC) can sit at 0 or 1 before
            it counts as a sustained integrity collapse rather than a
            brief dip. Default 60 s.
    """

    teleport_kt: float = 1000.0
    turn_rate_deg_s: float = 10.0
    speed_delta_kt: float = 50.0
    speed_delta_pct: float = 0.30
    vrate_delta_fpm: float = 2000.0
    nic_floor_s: float = 60.0


def to_parameters(config: SpoofingConfig) -> dict:
    """Turn a SpoofingConfig into a plain dict, to record on each alert.

    Args:
        config: The config whose limits should be recorded.

    Returns:
        A dict mapping each limit's field name to its value.
    """
    return asdict(config)
