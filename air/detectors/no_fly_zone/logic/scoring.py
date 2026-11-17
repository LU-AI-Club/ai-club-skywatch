"""Stream G - score, severity, and the Detection contract.

Turns the upstream stage results into one :class:`Detection`. This is the only
module that decides how bad something is, so the whole policy is readable in
one place.

Scoring shape
-------------
Start from ``scoring.base_by_zone_type[zone.zone_type]``. Add a depth bump of
``scoring.depth_bump_per_nm`` per nautical mile of penetration, capped at
``scoring.depth_bump_max``. Subtract the weight of every
:class:`ContextSignal`. Clamp the result to ``[0.0, 1.0]``.

Severity caps
-------------
``activation.state is UNKNOWN``
    Cap at ``severity.unknown_activation_cap`` - we never treat a maybe-cold
    zone as a confirmed incursion.
``containment.contained is False`` but ``buffered_contained is True``
    Cap at ``severity.buffered_only`` - this may be position error, not a
    violation.
``zone.zone_type`` listed in ``severity.zone_type_cap``
    Cap at the severity given for that type - a MOA is legal to fly through
    even when it is in use, so it never reaches the severity of a closed area.

Inputs
------
state, zone, containment, vertical, activation, signals, cfg:
    The outputs of streams A-F plus config.

Outputs
-------
One :class:`Detection`. ``baseline_or_model_version`` must come from
:meth:`Config.baseline_version`, which pins both the rules version and the
airspace publication cycle. ``explanation_facts`` must be reconstructable from
the inputs, and ``limitations`` must state what the detector could not check
(unknown activation, barometric-only altitude, or terrain-based AGL floors).

Confidence
----------
``raw_model_confidence`` is a bounded evidence-strength score, not a threat
score or calibrated probability. It combines configured activation, horizontal
position, and datum-appropriate altitude-source factors. Episode persistence
is added later by ``logic.episodes`` using elapsed timestamps from uninterrupted
runs of fired reports. Context signals affect anomaly score only.

Required ``extras`` keys
------------------------
``emit.to_platform_detection`` converts this Detection into the vendored
SENTINEL contract, which requires a timestamp and provenance that
``types.Detection`` does not carry. Put them in ``extras`` or emitting fails:

``observed_at``     the AircraftState timestamp (tz-aware UTC)
``source_row_id``   provenance back to the raw record
``lat`` / ``lon``   position, for the geospatial centroid

Also populate ``altitude_ft``, ``zone_id`` and ``penetration_nm`` when known -
they become the platform record's geospatial context. ``zone_type`` and
``signal_facts`` feed episode grouping (logic/episodes.py). ``zone_id``,
``zone_name`` and ``zone_type`` also fill the live table's zone columns
(see ``live.py``).

Failure causes
--------------
KeyError
    ``zone.zone_type`` has no entry in ``scoring.base_by_zone_type``. Config
    validation already guards this, so reaching it means config drifted.
ValueError
    Penetration distance is non-finite, the anomaly score is non-finite, or the
    effective position uncertainty is non-positive or non-finite. Only a missing
    uncertainty radius falls back to the configured default; invalid supplied
    values fail explicitly.

Notes
-----
No constants inline. Every number above comes from ``cfg``.
"""
from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Any

from ..config import Config
from ..types import (
    ActivationResult,
    ActivationState,
    AircraftState,
    AirspaceZone,
    AltitudeSource,
    ContainmentResult,
    ContextSignal,
    Datum,
    Detection,
    Severity,
    VerticalResult,
)

_METERS_PER_NAUTICAL_MILE = 1852.0

# Entity id prefix. MUST match the `observations.entity_id` form ('icao24:a1b2c3'):
# it is the only field downstream can join a detection back to a position on.
# air/live/payload.py strips this prefix on the way in, leaving AircraftState.icao24
# as bare hex, so the same one goes back on here. A different prefix silently
# matches nothing. See docs/live_integration/DETECTION_TABLE_COLUMNS.md.
ENTITY_PREFIX = "icao24:"


def entity_id_for(icao24: str) -> str:
    """``'a1b2c3'`` -> ``'icao24:a1b2c3'``, the id every consumer joins on."""
    return f"{ENTITY_PREFIX}{icao24}"


def build_detection(
    state: AircraftState,
    zone: AirspaceZone,
    containment: ContainmentResult,
    vertical: VerticalResult,
    activation: ActivationResult,
    signals: Sequence[ContextSignal],
    cfg: Config,
) -> Detection:
    """Score one incursion and emit an internal Detection.

    Raises:
        KeyError: The zone type has no configured base score.
        ValueError: A penetration distance, score input, or supplied uncertainty
            radius is invalid.
    """
    scoring = cfg["scoring"]
    base_score = float(scoring["base_by_zone_type"][zone.zone_type.value])
    penetration_nm = containment.penetration_nm
    if penetration_nm is not None and not isfinite(penetration_nm):
        raise ValueError("penetration distance must be finite")
    depth_nm = max(penetration_nm or 0.0, 0.0)
    depth_bump = min(
        depth_nm * float(scoring["depth_bump_per_nm"]),
        float(scoring["depth_bump_max"]),
    )
    context_penalty = sum(signal.weight for signal in signals)
    unbounded_score = base_score + depth_bump - context_penalty
    if not isfinite(unbounded_score):
        raise ValueError("scoring inputs must produce a finite score")
    anomaly_score = min(1.0, max(0.0, unbounded_score))

    severity = Severity.HIGH
    severity_caps = [severity]
    if activation.state is ActivationState.UNKNOWN:
        severity_caps.append(Severity(cfg["severity"]["unknown_activation_cap"]))
    if not containment.contained and containment.buffered_contained:
        severity_caps.append(Severity(cfg["severity"]["buffered_only"]))
    zone_type_cap = cfg["severity"].get("zone_type_cap", {}).get(zone.zone_type.value)
    if zone_type_cap is not None:
        severity_caps.append(Severity(zone_type_cap))
    severity_order = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH)
    severity = min(severity_caps, key=severity_order.index)

    confidence_cfg = scoring["confidence"]
    if activation.state is ActivationState.ACTIVE:
        activation_factor = float(confidence_cfg["active_activation_factor"])
    elif activation.state is ActivationState.UNKNOWN:
        activation_factor = float(confidence_cfg["unknown_activation_factor"])
    else:
        activation_factor = 0.0
    if containment.contained:
        uncertainty_m = containment.uncertainty_radius_m
        if uncertainty_m is None:
            uncertainty_m = float(cfg["geometry"]["default_uncertainty_m"])
        if not isfinite(uncertainty_m) or uncertainty_m <= 0.0:
            raise ValueError("position uncertainty radius must be positive and finite")
        penetration_m = max(penetration_nm or 0.0, 0.0) * _METERS_PER_NAUTICAL_MILE
        depth_fraction = min(penetration_m / uncertainty_m, 1.0)
        position_floor = float(confidence_cfg["strict_position_min_factor"])
        position_factor = position_floor + (1.0 - position_floor) * depth_fraction
    elif containment.buffered_contained:
        position_factor = float(confidence_cfg["buffered_position_factor"])
    else:
        position_factor = 0.0
    preferred_altitude_source = (
        AltitudeSource.BAROMETRIC
        if zone.floor_datum is Datum.FL and zone.ceiling_datum is Datum.FL
        else AltitudeSource.GEOMETRIC
    )
    if (
        vertical.altitude_source is AltitudeSource.NONE
        or vertical.altitude_ft is None
        or not vertical.within
    ):
        altitude_factor = 0.0
    elif vertical.altitude_source is preferred_altitude_source:
        altitude_factor = float(confidence_cfg["preferred_altitude_factor"])
    else:
        altitude_factor = float(confidence_cfg["fallback_altitude_factor"])
    per_report_confidence = min(
        1.0, max(0.0, activation_factor * position_factor * altitude_factor)
    )
    altitude = vertical.altitude_ft
    explanation_facts = [
        (
            f"Aircraft {state.icao24} was inside zone {zone.zone_id} "
            f"({zone.zone_type.value})."
            if containment.contained
            else f"Aircraft {state.icao24} was within the uncertainty buffer of "
            f"zone {zone.zone_id} ({zone.zone_type.value})."
        ),
        f"Zone activation was {activation.state.value.lower()}: {activation.basis}.",
        (
            f"Altitude {altitude:.0f} ft was within the zone's vertical band."
            if vertical.within and altitude is not None
            else "The aircraft did not have a comparable altitude inside the zone band."
        ),
        (
            "Geometric altitude is referenced to the WGS84 ellipsoid and was "
            "compared with an MSL/SFC limit without geoid correction."
            if vertical.altitude_source is AltitudeSource.GEOMETRIC
            and (zone.floor_datum in (Datum.MSL, Datum.SFC)
                 or zone.ceiling_datum in (Datum.MSL, Datum.SFC))
            else ""
        ),
        (
            f"Evidence confidence {per_report_confidence:.3f} = activation factor "
            f"{activation_factor:.3f} x position factor {position_factor:.3f} "
            f"x altitude factor {altitude_factor:.3f}."
        ),
        (
            f"Anomaly score {anomaly_score:.3f} = base {base_score:.3f} + "
            f"depth bump {depth_bump:.3f} - context penalty {context_penalty:.3f}."
        ),
    ]
    explanation_facts = [fact for fact in explanation_facts if fact]
    explanation_facts.extend(signal.fact for signal in signals)

    limitations: list[str] = []
    if activation.state is ActivationState.UNKNOWN:
        limitations.append("Zone activation could not be determined.")
    if vertical.altitude_source is AltitudeSource.BAROMETRIC:
        limitations.append(
            "Barometric altitude was used; it may be a fallback for non-FL limits "
            "or preferred for FL limits."
        )
    if (
        vertical.altitude_source is AltitudeSource.GEOMETRIC
        and (zone.floor_datum in (Datum.MSL, Datum.SFC)
             or zone.ceiling_datum in (Datum.MSL, Datum.SFC))
    ):
        limitations.append(
            "Geometric altitude is referenced to the WGS84 ellipsoid and was "
            "compared with an MSL/SFC limit without geoid correction."
        )
    if zone.floor_datum is Datum.AGL:
        limitations.append(
            "AGL floor was evaluated against bilinearly interpolated terrain from the offline grid."
        )
    if zone.ceiling_datum is Datum.AGL:
        limitations.append(
            "AGL ceiling was not evaluated because terrain-relative ceilings are unsupported."
        )
    if vertical.altitude_source is AltitudeSource.NONE or vertical.altitude_ft is None:
        limitations.append("No usable altitude was available.")

    extras: dict[str, Any] = {
        "observed_at": state.timestamp,
        "source_row_id": state.source_row_id,
        "lat": state.lat,
        "lon": state.lon,
        "zone_id": zone.zone_id,
        "zone_type": zone.zone_type.value,
        # For the live table's zone_name column (nullable; some SUA/TFR have none).
        "zone_name": zone.name or None,
        # The signal facts on their own, so episode grouping can say when a
        # signal (e.g. a squawk) first appeared during a crossing.
        "signal_facts": [signal.fact for signal in signals],
    }
    if altitude is not None:
        extras["altitude_ft"] = altitude
    if penetration_nm is not None:
        extras["penetration_nm"] = penetration_nm

    return Detection(
        detector_id=str(cfg["detector"]["id"]),
        detector_version=str(cfg["detector"]["version"]),
        entity_ids=(entity_id_for(state.icao24),),
        detection_type=str(cfg["detector"]["detection_type"]),
        severity=severity,
        anomaly_score=anomaly_score,
        raw_model_confidence=per_report_confidence,
        evidence_refs=(f"adsb:{state.source_row_id}", f"airspace:{zone.zone_id}"),
        feature_schema_version=str(cfg["detector"]["feature_schema_version"]),
        baseline_or_model_version=cfg.baseline_version,
        explanation_facts=tuple(explanation_facts),
        limitations=tuple(limitations),
        extras=extras,
    )
