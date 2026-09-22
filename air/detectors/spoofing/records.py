"""The two records the spoofing detector passes between its stages.

These are *contracts*: agreed shapes at a boundary. Freeze them early so each
lane can build against the shape instead of waiting for someone's code.

    AdsbObservation[]            (shared input contract, air/models/observation.py)
          |  features lane
          v
    SpoofingFeatureRecord[]      <- one per consecutive pair, within a segment
          |  physics / identity lanes
          v
    SpoofingEvent[]              <- one per rule hit
          |  scoring + output lane
          v
    Detection                    (shared output contract, contracts/)

Units are in the field names and never change downstream. Optional fields are
``None`` when the inputs did not carry them — that is normal, and rules must
abstain rather than guess when a value they need is ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SpoofingFeatureRecord:
    """What one consecutive pair of observations implies about an aircraft.

    Produced by the features lane from two ``AdsbObservation`` records in the
    same track segment. Every physics and identity rule reads these fields.

    ``prev_*`` / ``curr_*`` describe the two observations the record came from;
    the derived fields are what the rules actually test.
    """

    icao24: str
    segment_id: int
    prev_observed_at: datetime
    curr_observed_at: datetime

    # --- derived, the reason this record exists ---------------------------
    dt_s: float                              # seconds between the two reports
    dist_m: float                            # great-circle distance, metres
    implied_speed_kt: float | None = None    # dist_m / dt_s, in knots
    reported_speed_kt: float | None = None   # what the aircraft claimed
    speed_delta_kt: float | None = None      # implied - reported
    implied_vrate_fpm: float | None = None   # altitude change / dt_s
    reported_vrate_fpm: float | None = None  # what the aircraft claimed
    vrate_delta_fpm: float | None = None     # implied - reported
    turn_rate_dps: float | None = None       # heading change / dt_s, signed
    agl_ft: float | None = None              # altitude above terrain, if known

    # --- carried through for evidence and for the identity rules ----------
    prev_latitude: float | None = None
    prev_longitude: float | None = None
    curr_latitude: float | None = None
    curr_longitude: float | None = None
    altitude_ft: float | None = None
    nic: int | None = None
    nacp: int | None = None
    callsign: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.icao24, str) or not self.icao24.strip():
            raise ValueError("icao24 must be a non-blank string")
        if self.dt_s <= 0:
            raise ValueError("dt_s must be positive; drop non-positive pairs instead")
        if self.dist_m < 0:
            raise ValueError("dist_m must not be negative")

    @property
    def feature_schema_version(self) -> str:
        """Stamped onto every Detection so an alert stays interpretable."""
        return "air-features-v1"


@dataclass(frozen=True, slots=True)
class SpoofingEvent:
    """One rule hit: what fired, on what evidence, and by how much.

    Produced by the physics and identity lanes, consumed by the scoring and
    output lane. It deliberately carries no score and no severity — those are
    the scoring lane's job, computed from ``measured`` against ``threshold``.
    """

    gate: str                        # e.g. "teleport_v1"
    detection_type: str              # e.g. "position_jump"
    reason: str                      # short constant, e.g. "TELEPORT"
    icao24s: tuple[str, ...]         # one id, or several for identity findings
    observed_from: datetime          # start of the evidence window
    observed_to: datetime            # end of the evidence window

    measured: float | None = None    # the value that broke the rule
    threshold: float | None = None   # the limit it broke
    unit: str | None = None          # e.g. "kt", "fpm", "deg/s"

    latitude: float | None = None    # where to put it on a map
    longitude: float | None = None
    altitude_ft: float | None = None

    features: tuple[SpoofingFeatureRecord, ...] = ()   # the evidence
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("gate", "detection_type", "reason"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be a non-blank string")
        if not self.icao24s:
            raise ValueError("icao24s must name at least one aircraft")
        if self.observed_to < self.observed_from:
            raise ValueError("observed_to must not be before observed_from")

    def to_parameters(self) -> dict[str, Any]:
        """Flat view of the event, handy for Detection metadata."""
        return {f.name: getattr(self, f.name) for f in fields(self) if f.name != "features"}


__all__ = ["SpoofingFeatureRecord", "SpoofingEvent"]
