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

    vrate_delta_fpm: float = 2000.0
    """Above barometric noise and sensor lag; a normal climb is 1500-2500."""

    altitude_quantum_ft: float = 25.0
    """The step size altitude is reported in.

    This feed rounds altitude to 25 ft. A level aircraft therefore appears to
    jump a whole step at a time, and over a short gap that implies a large
    climb rate purely as an artefact: 25 ft in 0.55 s reads as 2,727 fpm.
    Without accounting for it, 96% of all alerts on the real file were level
    aircraft tripping the vertical-rate rule.
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
