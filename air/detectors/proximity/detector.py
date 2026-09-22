"""skywatch.proximity — predicted closest-approach detector for aircraft pairs.

Same skeleton as air/detectors/_example_altitude, with a harder middle:

    config (proximity.yaml)
      -> tracks.align_tracks        every aircraft on one 1-s clock
      -> pairs.candidate_pairs      nearby, airborne, not stacked
      -> features.pair_geometry     relative vectors, t_cpa, predicted separation
      -> rules.flag_pair            gates + threshold table       <- CalebK
      -> to_detection               the SENTINEL Detection contract
      -> ProximityDetector          wires it all together         <- Paul

This file holds the LAST stage only: scoring, the Detection contract, and the
detector class. The math is in geometry.py, the feature record in features.py,
the thresholds in rules.py.

We predict FUTURE separation, not current distance. Two aircraft 6 nm apart
and closing head-on are a detection; two aircraft 1 nm apart and diverging are
not.

Governance (do not violate):
  * explanation facts state distance, altitude gap and time to closest
    approach. Never "dangerous", never "violation". We report an observation;
    TCE/CAATS decides what it means.
  * we do not compute Trust. ``confidence`` is how sure we are the geometry is
    what we say it is — not how threatening it is.
"""

from __future__ import annotations

from datetime import timedelta

from air.detectors.proximity.config import ProximityConfig, load_config
from air.detectors.proximity.features import PairGeometry, pair_geometry
from air.detectors.proximity.pairs import candidate_pairs
from air.detectors.proximity.rules import flag_pair, severity_for
from air.detectors.proximity.tracks import align_tracks
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

DOMAIN = "air"
DETECTION_TYPE = "predicted_proximity"
FEATURE_SCHEMA_VERSION = "air-features-v1"


# --- Scoring + output (done) --------------------------------------------------
def confidence_for(geom: PairGeometry, cfg: ProximityConfig) -> float:
    """DONE. How sure we are about the geometry (NOT how threatening it is).

    Straight-line prediction degrades with lookahead, so confidence falls
    linearly from 1.0 at t_cpa = 0 to 0.5 at t_cpa = max_tcpa_s. Data quality
    (nic/nacp) can lower it further later — leave that to the false-positive
    lane.
    """
    assert geom.t_cpa_s is not None
    frac = min(1.0, max(0.0, geom.t_cpa_s / cfg.max_tcpa_s))
    return round(1.0 - 0.5 * frac, 3)


def explanation_facts(geom: PairGeometry) -> list[str]:
    """DONE. Observations only. Numbers, units, no adjectives."""
    assert geom.t_cpa_s is not None
    assert geom.predicted_horizontal_nm is not None and geom.predicted_vertical_ft is not None
    return [
        f"Current horizontal separation {geom.horizontal_now_nm:.2f} nm.",
        f"Current vertical separation {geom.vertical_now_ft:.0f} ft.",
        f"Closure rate {geom.closure_rate_kt:.0f} kt.",
        f"Time to closest approach {geom.t_cpa_s:.0f} s assuming constant speed and track.",
        f"Predicted separation at closest approach {geom.predicted_horizontal_nm:.2f} nm horizontal, "
        f"{geom.predicted_vertical_ft:.0f} ft vertical.",
    ]


LIMITATIONS = [
    "Prediction assumes constant ground speed and track for both aircraft.",
    "Positions are linearly interpolated between received reports.",
    "Controller clearances and intent are not observable from ADS-B.",
    "Barometric altitude is used; geometric altitude is ignored.",
]


def to_detection(geom: PairGeometry, severity: SeverityLevel, cfg: ProximityConfig) -> Detection:
    """DONE. Fill the SENTINEL Detection contract for one pair at one instant."""
    assert geom.t_cpa_s is not None
    a, b = geom.obs_a, geom.obs_b
    ref_a = f"{a.icao24}@{a.observed_at.isoformat()}"
    ref_b = f"{b.icao24}@{b.observed_at.isoformat()}"
    confidence = confidence_for(geom, cfg)
    facts = explanation_facts(geom)

    provenance = ProvenanceRecord(
        source_system="skywatch",
        raw_source_ref=f"{ref_a}|{ref_b}",
        processing_chain=(
            ProcessingStep(
                timestamp=geom.at,
                step_name="proximity_detection",
                transform_id=cfg.detector_id,
                transform_version=cfg.detector_version,
                parameters=cfg.to_parameters(),
            ),
        ),
    )
    cpa_time = geom.at + timedelta(seconds=geom.t_cpa_s)
    mid_lat = (a.latitude + b.latitude) / 2
    mid_lon = (a.longitude + b.longitude) / 2
    mid_alt = None
    if a.altitude_ft is not None and b.altitude_ft is not None:
        mid_alt = (a.altitude_ft + b.altitude_ft) / 2

    return Detection(
        detector_id=cfg.detector_id,
        detector_version=cfg.detector_version,
        detection_type=DETECTION_TYPE,
        severity=severity,
        confidence=confidence,
        temporal_bounds=TimeBounds(start_time=geom.at, end_time=cpa_time),
        provenance=provenance,
        entities_involved=[
            EntityRef(entity_id=f"aircraft:{a.icao24}", entity_type="aircraft", domain=DOMAIN),
            EntityRef(entity_id=f"aircraft:{b.icao24}", entity_type="aircraft", domain=DOMAIN),
        ],
        evidence=[
            Evidence(
                evidence_type="predicted_closest_approach",
                summary=facts[-1],
                source_ref=ref_a,
                entity_id=f"aircraft:{a.icao24}",
                confidence=confidence,
                timestamp=geom.at,
                metadata={
                    "t_cpa_s": geom.t_cpa_s,
                    "predicted_horizontal_nm": geom.predicted_horizontal_nm,
                    "predicted_vertical_ft": geom.predicted_vertical_ft,
                    "horizontal_now_nm": geom.horizontal_now_nm,
                    "vertical_now_ft": geom.vertical_now_ft,
                    "closure_rate_kt": geom.closure_rate_kt,
                },
            ),
            Evidence(
                evidence_type="aircraft_state",
                summary=f"{b.icao24} at {b.altitude_ft:.0f} ft, {b.ground_speed_kt:.0f} kt, track {b.track_deg:.0f}.",
                source_ref=ref_b,
                entity_id=f"aircraft:{b.icao24}",
                timestamp=b.observed_at,
            ),
        ],
        geospatial_context=GeoContext(
            centroid=GeoPosition(latitude=mid_lat, longitude=mid_lon, altitude=mid_alt),
            distance_meters=geom.horizontal_now_nm * 1852.0,
        ),
        metadata={
            "explanation_facts": facts,
            "limitations": list(LIMITATIONS),
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "baseline_or_model_version": cfg.config_version,
            "anomaly_score": confidence,  # placeholder until the evaluation lane defines it
            "raw_model_confidence": confidence,
        },
    )


# --- The detector (Paul wires detect_observations) ----------------------------
class ProximityDetector(BaseDetector):
    detector_id = "skywatch.proximity"
    detector_version = "0.1.0"
    domain = DOMAIN
    implementation_type = DetectorImplementationType.RULE_BASED

    def __init__(self, config: ProximityConfig | None = None) -> None:
        self.config = config or load_config()
        super().__init__()

    def get_required_data(self) -> DataRequirements:
        return DataRequirements(
            observation_types=("adsb_position",),
            source_names=("adsb",),
            auxiliary_data_keys=("observations",),
        )

    def detect_observations(self, observations: list[AdsbObservation]) -> list[Detection]:
        """Run the whole pipeline on a bag of raw observations.

        One Detection per aircraft PAIR, not per second: a 90-second encounter
        is one event. Keep, for each pair, the instant with the smallest
        predicted horizontal separation.

            snapshots = align_tracks(observations, cfg)
            best: dict[(icao_a, icao_b), (PairGeometry, SeverityLevel)] = {}
            for tick, snapshot in snapshots.items():
                for a, b in candidate_pairs(snapshot, cfg):
                    geom = pair_geometry(a, b)
                    if geom is None: continue
                    sev = flag_pair(geom, cfg)
                    if sev is None: continue
                    keep it if it is the first for this pair, or closer than
                    the one already kept
            return [to_detection(geom, sev, cfg) for geom, sev in best.values()]
        """
        raise NotImplementedError("TODO Paul: see docstring above and the tests")

    def detect(self, context: DetectionContext) -> list[Detection]:
        """BaseDetector entry point (same convention as the example detector)."""
        observations = list(context.auxiliary_data.get("observations", []))
        return self.detect_observations(observations)


__all__ = [
    "DETECTION_TYPE",
    "FEATURE_SCHEMA_VERSION",
    "LIMITATIONS",
    "ProximityDetector",
    "confidence_for",
    "explanation_facts",
    "to_detection",
]
