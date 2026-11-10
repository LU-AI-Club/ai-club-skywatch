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

from datetime import datetime, timedelta, timezone

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
# NACp (Navigation Accuracy Category - Position) is the 95% containment radius
# the aircraft itself reports for its position, in nautical miles. A pair whose
# positions could each be off by a third of a mile cannot support a claim about
# a half-mile predicted miss, so it lowers our confidence.
NACP_RADIUS_NM: dict[int, float] = {
    11: 0.002, 10: 0.005, 9: 0.016, 8: 0.05, 7: 0.1,
    6: 0.3, 5: 0.5, 4: 1.0, 3: 2.0, 2: 4.0, 1: 10.0,
}
UNKNOWN_NACP_RADIUS_NM = 0.3   # treat "not reported" as NACp 6
MIN_POSITION_QUALITY = 0.3     # never discount a detection to nothing


def position_quality(geom: PairGeometry, cfg: ProximityConfig) -> float:
    """DONE. How much the aircraft's own reported position accuracy is worth, 0.3-1.0.

    Taken against the tightest horizontal threshold we have: if the reported
    uncertainty is as large as the HIGH limit, the predicted separation tells
    us very little. Uses the WORSE of the two aircraft.
    """
    tightest = min((t.max_horizontal_nm for t in cfg.tiers), default=0.5)
    radii = [
        NACP_RADIUS_NM.get(obs.nacp, UNKNOWN_NACP_RADIUS_NM)
        if obs.nacp is not None else UNKNOWN_NACP_RADIUS_NM
        for obs in (geom.obs_a, geom.obs_b)
    ]
    worst = max(radii)
    return round(max(MIN_POSITION_QUALITY, min(1.0, 1.0 - worst / tightest)), 3)


def raw_model_confidence_for(geom: PairGeometry, cfg: ProximityConfig) -> float:
    """DONE. The detector's own certainty from the geometry alone, before any
    data-quality adjustment.

    Straight-line prediction degrades with lookahead, so this falls linearly
    from 1.0 at t_cpa = 0 to 0.5 at t_cpa = max_tcpa_s.
    """
    assert geom.t_cpa_s is not None
    frac = min(1.0, max(0.0, geom.t_cpa_s / cfg.max_tcpa_s))
    return round(1.0 - 0.5 * frac, 3)


def confidence_for(geom: PairGeometry, cfg: ProximityConfig) -> float:
    """DONE. How sure we are about the geometry (NOT how threatening it is).

    The raw geometric certainty, discounted by how well the two aircraft know
    where they are. This is the number we report; ``raw_model_confidence_for``
    is the same thing before the data-quality discount, so the two differ
    exactly when position reporting is poor.
    """
    return round(raw_model_confidence_for(geom, cfg) * position_quality(geom, cfg), 3)


def anomaly_score_for(geom: PairGeometry, cfg: ProximityConfig) -> float:
    """DONE. How far outside normal this encounter is, 0.0-1.0.

    A different question from confidence. "Normal" is the loosest tier we emit:
    a pair predicted to pass right on that boundary scores 0.0, and a predicted
    collision scores 1.0.

    Both dimensions have to be inside a tier for it to fire, so the binding
    constraint is whichever is proportionally closer to its limit -- that is the
    one that decides how anomalous the pair is.
    """
    assert geom.predicted_horizontal_nm is not None
    assert geom.predicted_vertical_ft is not None
    loosest_h = max((t.max_horizontal_nm for t in cfg.tiers), default=3.0)
    loosest_v = max((t.max_vertical_ft for t in cfg.tiers), default=900.0)
    worst_fraction = max(
        geom.predicted_horizontal_nm / loosest_h,
        geom.predicted_vertical_ft / loosest_v,
    )
    return round(max(0.0, min(1.0, 1.0 - worst_fraction)), 3)


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


def to_detection(
    geom: PairGeometry,
    severity: SeverityLevel,
    cfg: ProximityConfig,
    period_start: float | None = None,
) -> Detection:
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
    # The alert covers one cooldown period and predicts a closest approach
    # inside it. start_time is the period, which is epoch-anchored and so
    # identical from any window that covers it -- that is what makes
    # air.windowing.detection_dedup_key collapse the same alert seen twice
    # while keeping consecutive alerts about an ongoing encounter distinct.
    # end_time is the predicted closest approach. The evaluation tick is not
    # lost: it is on the evidence records and in the provenance chain.
    cpa_time = geom.at + timedelta(seconds=geom.t_cpa_s)
    cpa_time = cpa_time.replace(microsecond=0) + timedelta(
        seconds=1 if cpa_time.microsecond >= 500_000 else 0
    )
    if period_start is None:
        window_start = geom.at.replace(microsecond=0)
    else:
        window_start = datetime.fromtimestamp(period_start, tz=timezone.utc)
    if cpa_time < window_start:
        cpa_time = window_start

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
        temporal_bounds=TimeBounds(start_time=window_start, end_time=cpa_time),
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
            "anomaly_score": anomaly_score_for(geom, cfg),
            "raw_model_confidence": raw_model_confidence_for(geom, cfg),
            "position_quality": position_quality(geom, cfg),
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
        cfg = self.config
        snapshots = align_tracks(observations, cfg)

        # An encounter lasting minutes SHOULD produce several alerts -- the front
        # end groups them per pair. What it must not do is alert on every report.
        # So each pair may alert once per cooldown period, and the periods are
        # anchored to the epoch rather than to whichever tick we happened to see
        # first. That makes the grouping identical no matter how the runner
        # slices time, which is what lets two overlapping windows agree on the
        # same alert instead of emitting it twice.
        period = cfg.alert_cooldown_s
        best: dict[tuple[str, str, int], tuple[PairGeometry, SeverityLevel]] = {}

        for tick, snapshot in snapshots.items():
            slot = int(tick.timestamp() // period) if period > 0 else 0
            for a, b in candidate_pairs(snapshot, cfg):
                geom = pair_geometry(a, b)
                if geom is None:
                    continue

                severity = flag_pair(geom, cfg)
                if severity is None:
                    continue

                assert geom.predicted_horizontal_nm is not None
                # period 0 disables grouping: every tick is its own alert
                key = (a.icao24, b.icao24, slot if period > 0 else int(tick.timestamp()))
                previous = best.get(key)
                if previous is None:
                    best[key] = (geom, severity)
                    continue
                held, _ = previous
                assert held.predicted_horizontal_nm is not None
                if geom.predicted_horizontal_nm < held.predicted_horizontal_nm:
                    best[key] = (geom, severity)

        ordered = sorted(best.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1]))
        return [
            to_detection(geom, severity, cfg, period_start=slot * period if period > 0 else None)
            for (_, _, slot), (geom, severity) in ordered
        ]

    def detect(self, context: DetectionContext) -> list[Detection]:
        """BaseDetector entry point (same convention as the example detector)."""
        observations = list(context.auxiliary_data.get("observations", []))
        return self.detect_observations(observations)


__all__ = [
    "DETECTION_TYPE",
    "anomaly_score_for",
    "position_quality",
    "raw_model_confidence_for",
    "FEATURE_SCHEMA_VERSION",
    "LIMITATIONS",
    "ProximityDetector",
    "confidence_for",
    "explanation_facts",
    "to_detection",
]
