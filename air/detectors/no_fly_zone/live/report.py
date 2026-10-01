"""Run the real SkyWatch pipeline over one Flys Down snapshot.

Pure: takes parsed JSON and a clock reading, returns a JSON-ready report. The
runner does the network; tests drive this directly with fixtures.

What a report can say, and what it cannot
-----------------------------------------
``feed.status`` is ``fresh``, ``stale`` or ``unavailable``. Only a fresh feed
is evaluated. A stale or unavailable one yields ``evaluation.ran = false`` and
no detections, so "nothing found" and "nothing checked" never look alike.

Each detection has a ``classification``:

``confirmed_active``
    Strictly inside the polygon, inside the altitude band, and the zone's
    activation was ACTIVE from a published source. The strongest thing this
    integration can say, and still experimental: Flys Down's geometry is
    simplified and no NOTAM, TFR or waiver was checked.
``activation_uncertain``
    Inside the volume, but activation is UNKNOWN. Severity is capped by
    ``severity.unknown_activation_cap``. Not a violation claim.
``buffered_only``
    Outside the polygon but within position uncertainty. Severity is capped by
    ``severity.buffered_only``. May be position error.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from typing import Any

from ..config import Config
from ..emit import to_platform_detection
from ..geo.altitude import vertical_check
from ..geo.containment import check_containment
from ..logic.activation import is_active
from ..logic.context import gather_signals
from ..logic.detector import run
from ..types import ActivationState, AircraftState, AirspaceZone, Detection, ExitReason
from .feed import FRESH, FeedBatch, FeedStatus, map_feed
from .zones import ZoneBatch, map_zones

SCHEMA = "skywatch.flysdown.report/1"
CONFIRMED = "confirmed_active"
UNCERTAIN = "activation_uncertain"
BUFFERED = "buffered_only"

GLOBAL_LIMITATIONS = (
    "Experimental. Not for navigation, and not operational safety advice.",
    "Zone geometry and limits come from Flys Down's zones.json, which simplifies FAA "
    "boundaries and does not model NOTAMs, TFRs or activation times.",
    "No NOTAM, TFR or waiver source was checked. An aircraft inside a zone may be "
    "authorized to be there.",
    "Observation times are estimated from the feed's fetch time minus each position's "
    "age; the feed carries no per-aircraft timestamp.",
)
FEED_LIMITATIONS = (
    "Observation time estimated as feed fetchedAt minus seenPos; the relay's "
    "fetch-to-store delay is not measured, so the true time is slightly earlier.",
    "The feed carries no NIC or NACp, so position uncertainty is the configured default.",
    "Zone geometry is Flys Down's simplified copy of the FAA boundary.",
)


def live_config(cfg: Config, zones: ZoneBatch) -> Config:
    """Pin the airspace cycle to the zones actually used.

    config.yaml's ``source_asof`` describes the fixture file. Left alone it
    would stamp every live detection with the wrong cycle, which
    ``Config.baseline_version`` exists to prevent.
    """
    raw = dict(cfg.raw)
    airspace = dict(raw["airspace"])
    airspace["source_asof"] = zones.asof.isoformat() if zones.asof else "unknown"
    airspace["source"] = "flysdown"
    raw["airspace"] = airspace
    return Config(raw)


def build_report(
    feed_payload: Any,
    zones_geojson: Any,
    cfg: Config,
    live_cfg: Mapping[str, Any],
    received_at: datetime,
    *,
    feed_url: str | None = None,
    zones_error: str | None = None,
) -> dict[str, Any]:
    """Evaluate one snapshot. Never raises for bad feed data; it reports it."""
    scope = cfg["scope"]
    zones: ZoneBatch | None = None
    if zones_error is None:
        try:
            zones = map_zones(zones_geojson, live_cfg["zones"])
        except ValueError as exc:
            zones_error = str(exc)

    batch = map_feed(feed_payload, received_at, live_cfg["feed"], scope)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "experimental": True,
        "generatedAt": _iso(received_at),
        "detector": {
            "id": cfg["detector"]["id"],
            "version": cfg["detector"]["version"],
            "rulesVersion": cfg["detector"]["rules_version"],
        },
        "scope": {
            "name": scope["center_name"],
            "lat": scope["center_lat"],
            "lon": scope["center_lon"],
            "radiusNm": scope["radius_nm"],
        },
        "feed": _feed_json(batch.status, feed_url),
        "zones": _zones_json(zones, zones_error),
        "evaluation": {"ran": False, "reason": None},
        "detections": [],
        "limitations": list(GLOBAL_LIMITATIONS),
    }

    if zones is None or not zones.zones:
        report["evaluation"]["reason"] = f"zones unavailable: {zones_error or 'no usable zones'}"
        return report
    if batch.status.status != FRESH:
        report["evaluation"]["reason"] = f"feed {batch.status.status}: {batch.status.reason}"
        return report

    run_cfg = live_config(cfg, zones)
    report["detector"]["baseline"] = run_cfg.baseline_version
    exits: Counter[ExitReason] = Counter()
    by_row = {s.source_row_id: s for s in batch.states}
    by_zone = {z.zone_id: z for z in zones.zones}
    detections = list(run(batch.states, list(zones.zones), run_cfg, exits))
    items = [
        _detection_json(d, by_row, by_zone, zones, batch, run_cfg)
        for d in detections
    ]
    items.sort(key=lambda d: (-_CLASS_RANK[d["classification"]], -d["score"]))
    cap = int(live_cfg["publish"]["max_detections"])

    counts = Counter(item["classification"] for item in items)
    report["evaluation"] = {
        "ran": True,
        "reason": None,
        "statesEvaluated": len(batch.states),
        "skipped": dict(batch.skipped),
        "exits": {reason.value: n for reason, n in sorted(exits.items())},
        "detections": len(items),
        "confirmedActive": counts[CONFIRMED],
        "activationUncertain": counts[UNCERTAIN],
        "bufferedOnly": counts[BUFFERED],
        "truncated": max(0, len(items) - cap),
    }
    report["detections"] = items[:cap]
    return report


_CLASS_RANK = {CONFIRMED: 2, UNCERTAIN: 1, BUFFERED: 0}


def _detection_json(
    detection: Detection,
    by_row: Mapping[str, AircraftState],
    by_zone: Mapping[str, AirspaceZone],
    zones: ZoneBatch,
    batch: FeedBatch,
    cfg: Config,
) -> dict[str, Any]:
    extras = detection.extras
    state = by_row[str(extras["source_row_id"])]
    zone = by_zone[str(extras["zone_id"])]
    activation = is_active(zone, state.timestamp)
    contained = check_containment(state, [zone], cfg).contained
    if activation.state is ActivationState.UNKNOWN:
        classification = UNCERTAIN
    elif not contained:
        classification = BUFFERED
    else:
        classification = CONFIRMED

    timing = batch.timing[state.source_row_id]
    basis = zones.activation_basis.get(zone.zone_id, activation.basis)
    limitations = tuple(detection.limitations) + FEED_LIMITATIONS
    detection = replace(
        detection,
        limitations=limitations,
        explanation_facts=tuple(detection.explanation_facts) + (f"Activation basis: {basis}.",),
    )
    # The platform contract's own validation must accept what we publish.
    to_platform_detection(detection)
    scoring = _scoring(detection, state, zone, cfg)

    return {
        "aircraftId": state.icao24,
        "entityIds": list(detection.entity_ids),
        "callsign": state.callsign,
        "zoneId": zone.zone_id,
        "zoneName": zone.name,
        "zoneType": zone.zone_type.value,
        "classification": classification,
        "severity": detection.severity.value,
        "score": round(detection.anomaly_score, 3),
        "confidence": detection.raw_model_confidence,
        "scoring": scoring,
        "activation": activation.state.value,
        "activationBasis": basis,
        "lat": state.lat,
        "lon": state.lon,
        "altitudeFt": extras.get("altitude_ft"),
        "altitudeSource": vertical_check(state, zone).altitude_source.value,
        "penetrationNm": _round(extras.get("penetration_nm")),
        "observedAt": _iso(state.timestamp),
        "observedAtBasis": timing.basis,
        "seenPosS": timing.seen_pos_s,
        "positionAgeS": round(timing.position_age_s, 1),
        "sourceRowId": state.source_row_id,
        "feedSource": batch.status.source,
        "evidenceRefs": list(detection.evidence_refs),
        "baseline": detection.baseline_or_model_version,
        "explanation": list(detection.explanation_facts),
        "limitations": list(detection.limitations),
    }


def _scoring(
    detection: Detection, state: AircraftState, zone: AirspaceZone, cfg: Config
) -> dict[str, Any]:
    """The score's parts, from the same config and signals stream G used.

    Stream G only returns the total, so the parts are rebuilt here from the
    documented formula and checked against that total: if scoring.py ever
    changes shape, this raises instead of publishing parts that no longer add
    up to the score shown beside them.
    """
    scoring = cfg["scoring"]
    base = float(scoring["base_by_zone_type"][zone.zone_type.value])
    depth_nm = max(float(detection.extras.get("penetration_nm") or 0.0), 0.0)
    per_nm = float(scoring["depth_bump_per_nm"])
    cap = float(scoring["depth_bump_max"])
    depth_bump = min(depth_nm * per_nm, cap)
    signals = gather_signals(state, cfg)
    penalty = sum(s.weight for s in signals)
    total = min(1.0, max(0.0, base + depth_bump - penalty))
    if abs(total - detection.anomaly_score) > 1e-9:
        raise ValueError(
            f"score breakdown {total} does not match stream G's score {detection.anomaly_score}"
        )
    return {
        "formula": "clamp(base + min(depth_nm * per_nm, cap) - sum(context weights), 0, 1)",
        "base": base,
        "baseReason": f"zone type {zone.zone_type.value}",
        "depthNm": round(depth_nm, 3),
        "depthBumpPerNm": per_nm,
        "depthBumpCap": cap,
        "depthBump": round(depth_bump, 4),
        "contextSignals": [{"name": s.name, "weight": s.weight, "fact": s.fact} for s in signals],
        "contextPenalty": round(penalty, 4),
        "unclamped": round(base + depth_bump - penalty, 4),
        "score": round(detection.anomaly_score, 4),
        "severityCaps": _severity_caps(detection, cfg),
    }


def _severity_caps(detection: Detection, cfg: Config) -> list[str]:
    caps = []
    if "Zone activation could not be determined." in detection.limitations:
        caps.append(f"activation unknown: capped at {cfg['severity']['unknown_activation_cap']}")
    if detection.severity.value == cfg["severity"]["buffered_only"] and not caps:
        cap = cfg["severity"]["buffered_only"]
        caps.append(f"outside the polygon, within uncertainty: capped at {cap}")
    return caps


def _feed_json(status: FeedStatus, url: str | None) -> dict[str, Any]:
    return {
        "status": status.status,
        "reason": status.reason,
        "url": url,
        "source": status.source,
        "via": status.via,
        "fetchedAt": _iso(status.fetched_at) if status.fetched_at else None,
        "snapshotAgeS": _round(status.snapshot_age_s),
        "serverAgeMs": status.server_age_ms,
        "count": status.count,
    }


def _zones_json(zones: ZoneBatch | None, error: str | None) -> dict[str, Any]:
    if zones is None:
        return {"ok": False, "error": error, "used": [], "skipped": []}
    return {
        "ok": True,
        "source": "flysdown /data/zones.json",
        "asof": zones.asof.isoformat() if zones.asof else None,
        "disclaimer": zones.disclaimer,
        "used": [
            {
                "id": z.zone_id,
                "name": z.name,
                "type": z.zone_type.value,
                "activation": z.activation.value,
                "activationBasis": zones.activation_basis.get(z.zone_id),
            }
            for z in zones.zones
        ],
        "skipped": [{"id": zone_id, "reason": why} for zone_id, why in zones.skipped],
    }


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _round(value: Any) -> float | None:
    return round(float(value), 3) if isinstance(value, (int, float)) else None
