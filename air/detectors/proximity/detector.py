"""skywatch.proximity — predicted closest-approach detector for aircraft pairs.

Same skeleton as air/detectors/_example_altitude, with a harder middle:

    config (proximity.yaml)
      -> tracks.align_tracks        every aircraft on one 1-s clock
      -> pairs.candidate_pairs      nearby, airborne, not stacked
      -> pair_geometry              relative vectors, t_cpa, predicted separation
      -> flag_pair / severity_for   gates + threshold table       <- CalebK
      -> to_detection               the SENTINEL Detection contract
      -> ProximityDetector          wires it all together         <- Paul

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

from dataclasses import dataclass
from datetime import datetime, timedelta

from air.detectors.proximity.config import ProximityConfig, load_config
from air.detectors.proximity.geometry import (
    haversine_nm,
    predicted_separation,
    time_to_cpa,
    to_local_xy,
    velocity_xy,
)
from air.detectors.proximity.pairs import candidate_pairs
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


# --- The feature record (the contract between the math and the rules) --------
@dataclass(frozen=True, slots=True)
class PairGeometry:
    """Everything the rules need to know about one pair at one instant."""

    icao_a: str
    icao_b: str
    at: datetime
    horizontal_now_nm: float
    vertical_now_ft: float
    closure_rate_kt: float          # + means closing, - means opening
    t_cpa_s: float | None           # None when relative velocity is ~0
    predicted_horizontal_nm: float | None
    predicted_vertical_ft: float | None
    obs_a: AdsbObservation
    obs_b: AdsbObservation

    @property
    def converging(self) -> bool:
        return self.t_cpa_s is not None and self.t_cpa_s > 0


# --- Features (done; pure glue over geometry.py) ------------------------------
def pair_geometry(a: AdsbObservation, b: AdsbObservation) -> PairGeometry | None:
    """DONE. Relative state of the pair, or None if a needed field is missing."""
    if None in (a.altitude_ft, b.altitude_ft, a.ground_speed_kt, b.ground_speed_kt, a.track_deg, b.track_deg):
        return None
    assert a.altitude_ft is not None and b.altitude_ft is not None
    # Local plane centred on A, so A sits at the origin.
    bx, by = to_local_xy(b.latitude, b.longitude, a.latitude, a.longitude)
    avx, avy = velocity_xy(a.ground_speed_kt, a.track_deg)  # type: ignore[arg-type]
    bvx, bvy = velocity_xy(b.ground_speed_kt, b.track_deg)  # type: ignore[arg-type]
    rx, ry = bx, by
    vx, vy = bvx - avx, bvy - avy

    vertical_now = b.altitude_ft - a.altitude_ft
    vrate_diff = (b.vertical_rate_fpm or 0.0) - (a.vertical_rate_fpm or 0.0)
    dist_m = (rx * rx + ry * ry) ** 0.5
    # Closure rate = -(rate of change of distance) = -(r . v)/|r|, in knots.
    closure_mps = 0.0 if dist_m < 1e-6 else -(rx * vx + ry * vy) / dist_m
    closure_kt = closure_mps * 3600.0 / 1852.0

    t = time_to_cpa(rx, ry, vx, vy)
    if t is None:
        pred_h, pred_v = None, None
    else:
        pred_h, pred_v = predicted_separation(rx, ry, vx, vy, t, vertical_now, vrate_diff)

    return PairGeometry(
        icao_a=a.icao24,
        icao_b=b.icao24,
        at=a.observed_at,
        horizontal_now_nm=haversine_nm(a.latitude, a.longitude, b.latitude, b.longitude),
        vertical_now_ft=abs(vertical_now),
        closure_rate_kt=closure_kt,
        t_cpa_s=t,
        predicted_horizontal_nm=pred_h,
        predicted_vertical_ft=pred_v,
        obs_a=a,
        obs_b=b,
    )


# --- Rules (CalebK) -----------------------------------------------------------
def severity_for(
    predicted_horizontal_nm: float, predicted_vertical_ft: float, cfg: ProximityConfig
) -> SeverityLevel | None:
    """Look up the severity tier for a predicted separation, or None if none match.

    Walk ``cfg.tiers`` in order (HIGH first — the YAML lists them tightest to
    loosest) and return the first tier where BOTH hold:

        predicted_horizontal_nm < tier.max_horizontal_nm
        predicted_vertical_ft   < tier.max_vertical_ft

    Both must hold. 0.2 nm apart horizontally but 2000 ft apart vertically is
    normal, legal, and returns None.
    """
    raise NotImplementedError("TODO CalebK: see docstring above and the tests")


def flag_pair(geom: PairGeometry, cfg: ProximityConfig) -> SeverityLevel | None:
    """Apply the gates, then the threshold table. None means "do not emit".

    Gates, in order — fail any one and return None:
      1. ``geom.t_cpa_s`` is not None (relative velocity exists)
      2. ``geom.converging`` (closest approach is in the future, t_cpa > 0)
      3. ``geom.t_cpa_s <= cfg.max_tcpa_s`` (straight-line prediction is
         only trusted for the next couple of minutes)
      4. predicted separations are not None

    Then return ``severity_for(predicted_horizontal, predicted_vertical, cfg)``.
    """
    raise NotImplementedError("TODO CalebK: see docstring above and the tests")


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
    "PairGeometry",
    "ProximityDetector",
    "confidence_for",
    "explanation_facts",
    "flag_pair",
    "pair_geometry",
    "severity_for",
    "to_detection",
]
