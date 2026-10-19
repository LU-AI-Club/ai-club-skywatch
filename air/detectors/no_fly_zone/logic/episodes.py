"""Episode grouping (dedup) - one Detection per incursion, not per report.

The pipeline judges every position report on its own, so an aircraft that
spends 41 seconds inside a zone fires on each of its ~19 reports. This stage
groups those per-report detections into **episodes**: one aircraft in one zone
from entry to exit, emitted as a single Detection.

Rules
-----
open
    The first report that fires for an (aircraft, zone) pair. INFO
    (buffer-only) reports count, so "approaching inside the GPS buffer, then
    inside" is one episode, not two.
continue
    Every later report from that aircraft that fires for the same zone.
close
    ``dedup.clear_observations_to_close`` consecutive reports from that
    aircraft that do not fire for the zone (2 by default). Requiring more than
    one keeps a plane riding the boundary, or one jittery fix, from splitting
    an episode.
close on silence
    The aircraft sends nothing for more than ``sampling.max_gap_sec`` seconds
    (30 by default). Coverage drop-outs and low reporting rates (a small plane
    at the edge of range may report every 5-10 s) are why this is not tighter.
end of data
    Episodes still open when the reports run out are emitted as they stand.

The merged Detection
--------------------
anomaly_score
    The **peak** score over the episode.
severity / raw_model_confidence
    The highest over the episode (one strictly-inside HIGH report makes the
    episode HIGH even if its peak score came from a buffer-only report).
explanation_facts
    An episode summary first (zone, duration, report count, time span, peak),
    then the facts of the representative report (highest severity, then
    highest score), then any context signal first seen at another point in the
    episode, with when it appeared.
limitations
    Every limitation seen in any report, once each.
evidence_refs
    The ADS-B records of the entry, peak and exit reports, plus the zone.
extras
    The representative report's extras, plus ``episode_start``,
    ``episode_end``, ``dwell_sec``, ``report_count``, ``peak_score_at``,
    ``entry_source_row_id``, ``exit_source_row_id`` and the episode's deepest
    ``penetration_nm``. emit.py turns ``episode_start``/``episode_end`` into
    the platform contract's time bounds.

Inputs
------
reports:
    :class:`ReportResult` objects, **time-ordered per aircraft** (different
    aircraft may interleave). The detector sorts before calling.
cfg:
    Supplies ``dedup.clear_observations_to_close`` and ``sampling.max_gap_sec``.

Outputs
-------
An iterator of merged :class:`Detection`, each yielded when its episode
closes.

Failure causes
--------------
ValueError
    A report is older than the previous report for the same aircraft, or a
    fired Detection has no ``zone_id`` / ``observed_at`` in ``extras``.

Notes
-----
Pure: no I/O, and the only state lives inside one call. Aircraft are matched
case-insensitively on ``icao24``.
"""
from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..config import Config
from ..types import Detection, ReportResult, Severity

_SEVERITY_RANK = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3}


@dataclass
class _OpenEpisode:
    """Working state for one (aircraft, zone) episode inside a single call."""

    hits: list[tuple[datetime, Detection]] = field(default_factory=list)
    clear_streak: int = 0


def group_episodes(reports: Iterable[ReportResult], cfg: Config) -> Iterator[Detection]:
    """Group time-ordered reports into one merged Detection per episode."""
    clears_to_close = int(cfg["dedup"]["clear_observations_to_close"])
    max_gap_sec = float(cfg["sampling"]["max_gap_sec"])

    open_by_aircraft: dict[str, dict[str, _OpenEpisode]] = {}
    last_seen: dict[str, datetime] = {}

    for report in reports:
        aircraft = report.icao24.strip().lower()
        previous = last_seen.get(aircraft)
        if previous is not None and report.timestamp < previous:
            raise ValueError(
                f"reports for {aircraft} are not time-ordered: "
                f"{report.timestamp.isoformat()} came after {previous.isoformat()}"
            )
        last_seen[aircraft] = report.timestamp
        episodes = open_by_aircraft.setdefault(aircraft, {})

        # Silence long enough to break the track closes everything open.
        if previous is not None and (report.timestamp - previous).total_seconds() > max_gap_sec:
            for zone_id in list(episodes):
                yield _merge(episodes.pop(zone_id).hits)

        fired = {_zone_id(det): det for det in report.fired}

        # Open episodes this report did not fire for count toward closing.
        for zone_id in list(episodes):
            if zone_id in fired:
                continue
            episode = episodes[zone_id]
            episode.clear_streak += 1
            if episode.clear_streak >= clears_to_close:
                yield _merge(episodes.pop(zone_id).hits)

        for zone_id, det in fired.items():
            episode = episodes.setdefault(zone_id, _OpenEpisode())
            episode.hits.append((report.timestamp, det))
            episode.clear_streak = 0

    for episodes in open_by_aircraft.values():
        for episode in episodes.values():
            yield _merge(episode.hits)


def _zone_id(det: Detection) -> str:
    zone_id = det.extras.get("zone_id")
    if not zone_id:
        raise ValueError("a fired Detection has no extras['zone_id']; episodes need it")
    return str(zone_id)


def _merge(hits: list[tuple[datetime, Detection]]) -> Detection:
    """Collapse one episode's per-report detections into a single Detection."""
    first_at, first = hits[0]
    last_at, last = hits[-1]
    peak_at, peak = max(hits, key=lambda h: h[1].anomaly_score)
    _, rep = max(hits, key=lambda h: (_SEVERITY_RANK[h[1].severity], h[1].anomaly_score))

    zone_id = _zone_id(rep)
    dwell_sec = (last_at - first_at).total_seconds()
    zone_label = _zone_label(rep, zone_id)

    facts = [
        f"Aircraft {_aircraft(rep)} was in zone {zone_label} for {dwell_sec:.0f} s "
        f"across {len(hits)} report{'s' if len(hits) != 1 else ''}, "
        f"{first_at:%H:%M:%S}-{last_at:%H:%M:%S} UTC; peak anomaly score "
        f"{peak.anomaly_score:.3f} at {peak_at:%H:%M:%S}.",
        *rep.explanation_facts,
    ]
    # Context signals that showed up elsewhere in the episode, with first sighting.
    rep_signals = set(rep.extras.get("signal_facts", ()))
    first_seen: dict[str, datetime] = {}
    for at, det in hits:
        for fact in det.extras.get("signal_facts", ()):
            first_seen.setdefault(fact, at)
    for fact, at in first_seen.items():
        if fact not in rep_signals:
            offset = (at - first_at).total_seconds()
            facts.append(f"{fact} (first seen {at:%H:%M:%S}, {offset:.0f} s after entry).")

    limitations: list[str] = []
    for _, det in hits:
        for limit in det.limitations:
            if limit not in limitations:
                limitations.append(limit)

    evidence: list[str] = []
    for det in (first, peak, last):
        for ref in det.evidence_refs:
            if ref not in evidence:
                evidence.append(ref)

    penetrations = [
        float(p) for _, det in hits if (p := det.extras.get("penetration_nm")) is not None
    ]
    extras: dict[str, Any] = dict(rep.extras)
    extras.update(
        episode_start=first_at,
        episode_end=last_at,
        dwell_sec=dwell_sec,
        report_count=len(hits),
        peak_score_at=peak_at,
        entry_source_row_id=first.extras.get("source_row_id"),
        exit_source_row_id=last.extras.get("source_row_id"),
    )
    if penetrations:
        extras["penetration_nm"] = max(penetrations)

    return Detection(
        detector_id=rep.detector_id,
        detector_version=rep.detector_version,
        entity_ids=rep.entity_ids,
        detection_type=rep.detection_type,
        severity=rep.severity,
        anomaly_score=peak.anomaly_score,
        raw_model_confidence=max(det.raw_model_confidence for _, det in hits),
        evidence_refs=tuple(evidence),
        feature_schema_version=rep.feature_schema_version,
        baseline_or_model_version=rep.baseline_or_model_version,
        explanation_facts=tuple(facts),
        limitations=tuple(limitations),
        extras=extras,
    )


def _aircraft(det: Detection) -> str:
    entity = det.entity_ids[0] if det.entity_ids else "aircraft:unknown"
    return entity.split(":", 1)[-1]


def _zone_label(det: Detection, zone_id: str) -> str:
    """'P-901 (PROHIBITED)' when the zone type is known, else just the id."""
    zone_type = det.extras.get("zone_type")
    return f"{zone_id} ({zone_type})" if zone_type else zone_id
