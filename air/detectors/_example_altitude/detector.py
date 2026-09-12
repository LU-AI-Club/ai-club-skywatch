"""Example detector: flag aircraft outside an allowed altitude band.

THIS IS THE REFERENCE. It is deliberately trivial so the *shape* is obvious.
Every real detector (spoofing, proximity, no-fly-zone) is this same skeleton
with a harder middle:

    config (thresholds)  ->  a pure flag function  ->  confidence + severity
                                                     ->  emit the Detection contract
                                                     ->  a BaseDetector subclass

Read it top to bottom. Notice there is NO database and NO network anywhere:
every function takes plain objects and returns plain objects, so every one is
unit-testable on a hand-built fixture. See tests/air/detectors/test_example_altitude.py.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from air.models.observation import AdsbObservation
from contracts import (
    BaseDetector,
    DataRequirements,
    DetectionContext,
    Detection,
    DetectorImplementationType,
    EntityRef,
    Evidence,
    GeoContext,
    GeoPosition,
    ProcessingStep,
    ProvenanceRecord,
    SeverityLevel,
    TimeBounds,
)

DETECTOR_ID = "skywatch.example_altitude"
DETECTOR_VERSION = "0.1.0"
DOMAIN = "air"
DETECTION_TYPE = "altitude_band_violation"


# --- Config (the "baseline / reference" — what counts as normal) -------------
@dataclass(frozen=True, slots=True)
class ExampleAltitudeConfig:
    floor_ft: float = 500.0
    ceiling_ft: float = 60000.0
    detector_id: str = DETECTOR_ID
    detector_version: str = DETECTOR_VERSION

    def __post_init__(self) -> None:
        if self.ceiling_ft <= self.floor_ft:
            raise ValueError("ceiling_ft must be greater than floor_ft")

    def to_parameters(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# --- Core logic (a pure function) --------------------------------------------
def flag_altitude(obs: AdsbObservation, cfg: ExampleAltitudeConfig) -> str | None:
    """Return a reason string if this observation is out of band, else None.

    Pure: same input always gives same output, no side effects. This is the
    property that makes it trivial to test.
    """
    if obs.altitude_ft is None:
        return None  # can't judge what wasn't reported -> abstain (fail safe)
    if obs.altitude_ft < cfg.floor_ft:
        return "BELOW_FLOOR"
    if obs.altitude_ft > cfg.ceiling_ft:
        return "ABOVE_CEILING"
    return None


# --- Scoring (pure functions) ------------------------------------------------
def altitude_confidence(obs: AdsbObservation, cfg: ExampleAltitudeConfig) -> float:
    """How far out of band, normalized to 0..1. Farther out = more confident."""
    assert obs.altitude_ft is not None
    if obs.altitude_ft < cfg.floor_ft:
        overshoot = cfg.floor_ft - obs.altitude_ft
    else:
        overshoot = obs.altitude_ft - cfg.ceiling_ft
    # 0 ft over the line -> 0.5; 2000 ft or more over -> 1.0.
    return round(min(1.0, 0.5 + 0.5 * min(overshoot, 2000.0) / 2000.0), 3)


def altitude_severity(obs: AdsbObservation, cfg: ExampleAltitudeConfig) -> SeverityLevel:
    assert obs.altitude_ft is not None
    if obs.altitude_ft < cfg.floor_ft:
        overshoot = cfg.floor_ft - obs.altitude_ft
    else:
        overshoot = obs.altitude_ft - cfg.ceiling_ft
    return SeverityLevel.HIGH if overshoot >= 1000.0 else SeverityLevel.MEDIUM


# --- Output (fill in the real Detection contract) ----------------------------
def to_detection(
    obs: AdsbObservation, reason: str, cfg: ExampleAltitudeConfig
) -> Detection:
    provenance = ProvenanceRecord(
        source_system="skywatch",
        raw_source_ref=f"{obs.icao24}@{obs.observed_at.isoformat()}",
        processing_chain=(
            ProcessingStep(
                timestamp=obs.observed_at,
                step_name="example_altitude_detection",
                transform_id=cfg.detector_id,
                transform_version=cfg.detector_version,
                parameters=cfg.to_parameters(),
            ),
        ),
    )
    fact = (
        f"Altitude {obs.altitude_ft:.0f} ft is {reason.replace('_', ' ').lower()} "
        f"the allowed band [{cfg.floor_ft:.0f}, {cfg.ceiling_ft:.0f}] ft."
    )
    return Detection(
        detector_id=cfg.detector_id,
        detector_version=cfg.detector_version,
        detection_type=DETECTION_TYPE,
        severity=altitude_severity(obs, cfg),
        confidence=altitude_confidence(obs, cfg),
        temporal_bounds=TimeBounds(start_time=obs.observed_at, end_time=obs.observed_at),
        provenance=provenance,
        entities_involved=[
            EntityRef(entity_id=f"aircraft:{obs.icao24}", entity_type="aircraft", domain=DOMAIN)
        ],
        evidence=[
            Evidence(
                evidence_type="altitude_reading",
                summary=fact,
                confidence=altitude_confidence(obs, cfg),
                timestamp=obs.observed_at,
                metadata={"altitude_ft": obs.altitude_ft, "reason": reason},
            )
        ],
        geospatial_context=GeoContext(
            centroid=GeoPosition(
                latitude=obs.latitude, longitude=obs.longitude, altitude=obs.altitude_ft
            )
        ),
        metadata={"explanation_facts": [fact], "reason": reason},
    )


# --- The detector class (the BaseDetector contract) --------------------------
class ExampleAltitudeDetector(BaseDetector):
    detector_id = DETECTOR_ID
    detector_version = DETECTOR_VERSION
    domain = DOMAIN
    implementation_type = DetectorImplementationType.RULE_BASED

    def __init__(self, config: ExampleAltitudeConfig | None = None) -> None:
        self.config = config or ExampleAltitudeConfig()
        super().__init__()

    def get_required_data(self) -> DataRequirements:
        return DataRequirements(
            observation_types=("adsb_position",),
            source_names=("adsb",),
            auxiliary_data_keys=("observations",),
        )

    def detect_observations(self, observations: list[AdsbObservation]) -> list[Detection]:
        """Convenience entry point: run directly on a list of observations."""
        out: list[Detection] = []
        for obs in observations:
            reason = flag_altitude(obs, self.config)
            if reason is not None:
                out.append(to_detection(obs, reason, self.config))
        return out

    def detect(self, context: DetectionContext) -> list[Detection]:
        """BaseDetector entry point. Reads AdsbObservation objects placed in
        ``context.auxiliary_data['observations']`` (kept out of the mapping-only
        ``context.observations`` field so we can pass real dataclasses)."""
        observations = list(context.auxiliary_data.get("observations", []))
        return self.detect_observations(observations)
