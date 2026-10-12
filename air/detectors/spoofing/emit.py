"""Building the alert: the only thing the rest of SENTINEL ever sees.

Everything the team builds reaches the outside world through this file. A good
alert shows its work, so a reader can redo the arithmetic and decide for
themselves.

Two standing rules:

* **Facts, not conclusions.** "Position moved 47.3 nm in 8.00 s" is ours to
  say. "This aircraft is spoofing" is not -- TCE/CAATS owns that call.
* **``trust_assessment`` stays empty.** Trust, Risk and Assurance are the
  platform's to compute from our evidence.
"""

from __future__ import annotations

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.records import SpoofingEvent
from air.detectors.spoofing.scoring import confidence_for, score_for, severity_for
from contracts import (
    Detection,
    EntityRef,
    Evidence,
    GeoContext,
    GeoPosition,
    ProcessingStep,
    ProvenanceRecord,
    TimeBounds,
)

DETECTOR_ID = "skywatch.spoofing"
DETECTOR_VERSION = "0.1.0"
DOMAIN = "air"
FEATURE_SCHEMA_VERSION = "air-features-v1"

# What each gate means in plain words, for the first explanation sentence.
_GATE_PHRASE: dict[str, str] = {
    "teleport_v1": "implied ground speed exceeds what any aircraft can fly",
    "turn_rate_v1": "turn rate exceeds what the airframe can sustain",
    "speed_delta_v1": "reported ground speed disagrees with the positions",
    "vrate_delta_v1": "reported vertical rate disagrees with the altitudes",
    "nic_floor_v1": "navigation integrity stayed at the floor",
    "subterrain_v1": "reported position lies below the terrain",
    "coexistence_v1": "one identity reported from two unreachable places",
    "pingpong_v1": "position alternated between two places, each hop impossible",
    "reappear_v1": "track resumed beyond reachable distance after a gap",
    "registry_mismatch_v1": "performance contradicts the registered aircraft",
    "identity_drift_v1": "one identity carried more than one callsign",
}


def explanation_facts(event: SpoofingEvent) -> list[str]:
    """Plain sentences stating what was observed, for a human reader.

    Facts only: what we measured, what the limit was, and what the aircraft
    itself claimed. Never an interpretation. Every sentence has to be
    checkable against the evidence attached to the same detection.
    """
    facts: list[str] = []

    phrase = _GATE_PHRASE.get(event.gate)
    if phrase:
        facts.append(f"Gate {event.gate}: {phrase}.")

    if event.measured is not None and event.threshold is not None:
        unit = f" {event.unit}" if event.unit else ""
        facts.append(
            f"Measured {event.measured:,.1f}{unit} against a limit of "
            f"{event.threshold:,.1f}{unit}."
        )

    for feature in event.features[:1]:
        facts.append(
            f"Position moved {feature.dist_m / 1852.0:,.1f} nm in "
            f"{feature.dt_s:,.2f} s."
        )
        if feature.reported_speed_kt is not None:
            facts.append(
                f"Reported ground speed was {feature.reported_speed_kt:,.1f} kt."
            )

    window_s = (event.observed_to - event.observed_from).total_seconds()
    aircraft = ", ".join(event.icao24s)
    facts.append(
        f"Observed on aircraft {aircraft} over {window_s:,.0f} s "
        f"from {event.observed_from.isoformat()}."
    )
    return facts


def build_evidence(event: SpoofingEvent) -> list[Evidence]:
    """Attach the observations that prove the finding.

    One item per feature record behind the event, each carrying the
    arithmetic in its metadata so the alert can be rechecked without the
    original data in hand.
    """
    items: list[Evidence] = []
    for feature in event.features:
        items.append(
            Evidence(
                evidence_type="kinematic_pair",
                summary=(
                    f"{feature.icao24}: {feature.dist_m / 1852.0:,.1f} nm in "
                    f"{feature.dt_s:,.2f} s"
                ),
                entity_id=f"aircraft:{feature.icao24}",
                timestamp=feature.curr_observed_at,
                metadata={
                    "segment_id": feature.segment_id,
                    "dt_s": feature.dt_s,
                    "dist_m": feature.dist_m,
                    "implied_speed_kt": feature.implied_speed_kt,
                    "reported_speed_kt": feature.reported_speed_kt,
                    "turn_rate_dps": feature.turn_rate_dps,
                    "feature_schema_version": feature.feature_schema_version,
                },
            )
        )

    if not items:
        # Identity findings may rest on whole tracks rather than one pair.
        items.append(
            Evidence(
                evidence_type=event.detection_type,
                summary=f"{event.reason} on {', '.join(event.icao24s)}",
                timestamp=event.observed_to,
                metadata=dict(event.details),
            )
        )
    return items


def build_provenance(event: SpoofingEvent, cfg: SpoofingConfig) -> ProvenanceRecord:
    """Record what produced the alert and under which settings.

    A detection is only interpretable next to the limits that produced it.
    Change a threshold next week and yesterday's alerts must still say what
    they were measured against, so the whole config travels with every one.
    """
    return ProvenanceRecord(
        source_system="skywatch",
        raw_source_ref=f"{','.join(event.icao24s)}@{event.observed_from.isoformat()}",
        processing_chain=(
            ProcessingStep(
                timestamp=event.observed_to,
                step_name=event.gate,
                transform_id=DETECTOR_ID,
                transform_version=DETECTOR_VERSION,
                parameters=cfg.to_parameters(),
            ),
        ),
    )


def to_detection(event: SpoofingEvent, cfg: SpoofingConfig) -> Detection:
    """Build the final alert from one rule hit.

    Severity, confidence, evidence, provenance and temporal bounds are
    fields on the platform contract. Anomaly score, the explanation
    sentences, the gate and the limitations ride in ``metadata`` -- the same
    pattern the reference detector uses.

    ``trust_assessment`` is left unset on purpose.
    """
    score = score_for(event, cfg)
    confidence = confidence_for(event, cfg)
    facts = explanation_facts(event)

    centroid = None
    if event.latitude is not None and event.longitude is not None:
        centroid = GeoPosition(
            latitude=event.latitude,
            longitude=event.longitude,
            altitude=event.altitude_ft,
        )

    return Detection(
        detector_id=DETECTOR_ID,
        detector_version=DETECTOR_VERSION,
        detection_type=event.detection_type,
        severity=severity_for(event.gate),
        confidence=confidence,
        temporal_bounds=TimeBounds(
            start_time=event.observed_from, end_time=event.observed_to
        ),
        provenance=build_provenance(event, cfg),
        entities_involved=[
            EntityRef(entity_id=f"aircraft:{icao24}", entity_type="aircraft", domain=DOMAIN)
            for icao24 in event.icao24s
        ],
        evidence=build_evidence(event),
        geospatial_context=GeoContext(centroid=centroid),
        metadata={
            "gate": event.gate,
            "reason": event.reason,
            "anomaly_score": score,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "baseline_or_model_version": f"physics-gates-{DETECTOR_VERSION}",
            "explanation_facts": facts,
            "limitations": _limitations(event),
            "event": event.to_parameters(),
        },
    )


def _limitations(event: SpoofingEvent) -> list[str]:
    """What this detection honestly cannot tell you."""
    limits = [
        "Reports a deviation only; intent and threat are not assessed here.",
        "Single receiver: an injected transmission cannot be distinguished "
        "from a corrupted field on a real one.",
    ]
    if event.gate in {"registry_mismatch_v1", "identity_drift_v1", "coexistence_v1"}:
        limits.append(
            "Aircraft in the FAA Privacy ICAO Address programme are authorised "
            "to broadcast an alternate identity and look identical to this."
        )
    if event.measured is None:
        limits.append("No measurable quantity for this gate; score is nominal.")
    return limits


__all__ = [
    "explanation_facts",
    "build_evidence",
    "build_provenance",
    "to_detection",
]
