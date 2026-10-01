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
(unknown activation, barometric-only altitude, AGL floor not evaluated).

Required ``extras`` keys
------------------------
``emit.to_platform_detection`` converts this Detection into the vendored
SENTINEL contract, which requires a timestamp and provenance that
``types.Detection`` does not carry. Put them in ``extras`` or emitting fails:

``observed_at``     the AircraftState timestamp (tz-aware UTC)
``source_row_id``   provenance back to the raw record
``lat`` / ``lon``   position, for the geospatial centroid

Also populate ``altitude_ft``, ``zone_id`` and ``penetration_nm`` when known -
they become the platform record's geospatial context.

Failure causes
--------------
KeyError
    ``zone.zone_type`` has no entry in ``scoring.base_by_zone_type``. Config
    validation already guards this, so reaching it means config drifted.
ValueError
    The scoring inputs produce a non-finite score.

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
        ValueError: The score inputs produce a non-finite score.
    """
    scoring = cfg["scoring"]
    base_score = float(scoring["base_by_zone_type"][zone.zone_type.value])
    penetration_nm = containment.penetration_nm
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
    severity_order = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH)
    severity = min(severity_caps, key=severity_order.index)

    confirmed = (
        containment.contained
        and vertical.within
        and activation.state is ActivationState.ACTIVE
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
            f"Anomaly score {anomaly_score:.3f} = base {base_score:.3f} + "
            f"depth bump {depth_bump:.3f} - context penalty {context_penalty:.3f}."
        ),
    ]
    explanation_facts.extend(signal.fact for signal in signals)

    limitations: list[str] = []
    if activation.state is ActivationState.UNKNOWN:
        limitations.append("Zone activation could not be determined.")
    if vertical.altitude_source is AltitudeSource.BAROMETRIC:
        limitations.append(
            "Only barometric altitude was available; geometric altitude was unavailable."
        )
    if zone.floor_datum is Datum.AGL or zone.ceiling_datum is Datum.AGL:
        limitations.append(
            "AGL floor or ceiling was not evaluated because terrain data is unavailable."
        )
    if vertical.altitude_source is AltitudeSource.NONE:
        limitations.append("No usable altitude was available.")

    extras: dict[str, Any] = {
        "observed_at": state.timestamp,
        "source_row_id": state.source_row_id,
        "lat": state.lat,
        "lon": state.lon,
        "zone_id": zone.zone_id,
    }
    if altitude is not None:
        extras["altitude_ft"] = altitude
    if penetration_nm is not None:
        extras["penetration_nm"] = penetration_nm

    return Detection(
        detector_id=str(cfg["detector"]["id"]),
        detector_version=str(cfg["detector"]["version"]),
        entity_ids=(f"aircraft:{state.icao24}",),
        detection_type=str(cfg["detector"]["detection_type"]),
        severity=severity,
        anomaly_score=anomaly_score,
        raw_model_confidence=float(confirmed),
        evidence_refs=(f"adsb:{state.source_row_id}", f"airspace:{zone.zone_id}"),
        feature_schema_version=str(cfg["detector"]["feature_schema_version"]),
        baseline_or_model_version=cfg.baseline_version,
        explanation_facts=tuple(explanation_facts),
        limitations=tuple(limitations),
        extras=extras,
    )
