"""Shared data contracts for NoFlyZoneDetector.

LEAD-OWNED. Every module imports its inputs and outputs from here and from
nothing else in the package. Rules:
  - Dataclasses and enums only. No logic, no I/O, no network.
  - Everything is frozen: a stage never mutates what it was handed.
  - Changing a field is a team decision, made in a PR the lead reviews.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # shapely is only needed for type checking here
    from shapely.geometry.base import BaseGeometry


# ---------------------------------------------------------------- enums

class ZoneType(str, Enum):
    PROHIBITED = "PROHIBITED"
    RESTRICTED = "RESTRICTED"
    TFR = "TFR"
    WARNING = "WARNING"
    ALERT = "ALERT"
    MOA = "MOA"


class Datum(str, Enum):
    """Reference for an altitude value."""
    MSL = "MSL"   # feet above mean sea level
    AGL = "AGL"   # feet above ground level
    FL = "FL"     # flight level; value stored in feet (FL180 -> 18000)
    SFC = "SFC"   # the surface; value stored as 0


class Activation(str, Enum):
    """How a zone decides whether it is live."""
    ALWAYS = "ALWAYS"        # prohibited areas
    SCHEDULED = "SCHEDULED"  # published hours
    NOTAM = "NOTAM"          # activated by NOTAM, schedule unknown to us
    WINDOW = "WINDOW"        # explicit start/end, e.g. a TFR


class ActivationState(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"      # not a pass: caps severity downstream


class AltitudeSource(str, Enum):
    GEOMETRIC = "GEOMETRIC"
    BAROMETRIC = "BAROMETRIC"
    NONE = "NONE"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ExitReason(str, Enum):
    """Why a state left the pipeline without a detection."""
    NO_CANDIDATE = "no_candidate"
    OUTSIDE_POLYGON = "outside_polygon"
    VERTICAL_CLEAR = "vertical_clear"
    ZONE_INACTIVE = "zone_inactive"
    ON_GROUND = "on_ground"
    BAD_INPUT = "bad_input"


# ---------------------------------------------------------------- inputs

@dataclass(frozen=True, slots=True)
class AircraftState:
    """One observation of one aircraft. Produced by stream A (and I)."""
    icao24: str
    timestamp: datetime              # tz-aware UTC, always
    lat: float
    lon: float
    alt_baro_ft: float | None
    alt_geom_ft: float | None
    ground_speed_kt: float | None
    track_deg: float | None
    callsign: str | None
    squawk: str | None
    emitter_category: str | None
    nic: int | None
    nac_p: int | None
    on_ground: bool
    source_row_id: str               # provenance back to the raw record


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: datetime                  # tz-aware UTC
    end: datetime                    # tz-aware UTC, exclusive


@dataclass(frozen=True, slots=True)
class AirspaceZone:
    """One restricted volume. Produced by stream B."""
    zone_id: str                     # "P-56", "R-6601A", "TFR-5/0668"
    name: str
    zone_type: ZoneType
    geometry: BaseGeometry           # shapely, EPSG:4326, lon/lat order
    floor_ft: float
    floor_datum: Datum
    ceiling_ft: float
    ceiling_datum: Datum
    activation: Activation
    active_windows: tuple[TimeWindow, ...] = ()
    controlling_agency: str | None = None
    source: str = ""                 # e.g. "faa_sua"
    source_asof: date | None = None  # publication cycle of the source file


# ---------------------------------------------------------------- stage results

@dataclass(frozen=True, slots=True)
class ContainmentResult:
    """Stream C: horizontal check against candidate zones."""
    contained: bool                  # strict point-in-polygon
    buffered_contained: bool         # within position uncertainty of the zone
    zone_ids: tuple[str, ...]        # zones hit (strict or buffered)
    penetration_nm: float | None     # distance inside boundary; None if outside
    uncertainty_radius_m: float | None
    reason: ExitReason | None = None # set when nothing was hit


@dataclass(frozen=True, slots=True)
class VerticalResult:
    """Stream D: altitude against one zone's floor and ceiling."""
    within: bool
    altitude_ft: float | None        # value actually compared, after conversion
    altitude_source: AltitudeSource
    reason: ExitReason | None = None


@dataclass(frozen=True, slots=True)
class ActivationResult:
    """Stream E: was the zone live at the observation time."""
    state: ActivationState
    zone_id: str
    basis: str                       # e.g. "always active", "TFR window 1900Z-0130Z"


@dataclass(frozen=True, slots=True)
class ContextSignal:
    """Stream F: an observable fact that makes an incursion look authorized.

    Signals lower the score. They never prove approval.
    """
    name: str                        # key into config scoring.context_weights
    weight: float                    # filled from config, not hard-coded
    fact: str                        # human-readable, deterministic


# ---------------------------------------------------------------- output

@dataclass(frozen=True, slots=True)
class Detection:
    """Common SENTINEL Detection contract (syllabus section 6). Stream G."""
    detector_id: str
    detector_version: str
    entity_ids: tuple[str, ...]              # ("aircraft:ace81d",)
    detection_type: str
    severity: Severity
    anomaly_score: float
    raw_model_confidence: float
    evidence_refs: tuple[str, ...]
    feature_schema_version: str
    baseline_or_model_version: str
    explanation_facts: tuple[str, ...]
    limitations: tuple[str, ...]
    extras: dict[str, Any] = field(default_factory=dict)  # dwell, zone_id, etc.

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        for k in ("entity_ids", "evidence_refs", "explanation_facts", "limitations"):
            d[k] = list(d[k])
        return d
