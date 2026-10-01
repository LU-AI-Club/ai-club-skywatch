"""Plain-text view of one live report, for a terminal.

Pure: a report dict in, a string out. The rules match the Flys Down page: a
run that could not evaluate says so and never reads as "nothing found", and
every detection shows the arithmetic behind its score.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

_CLASS_WORDS = {
    "confirmed_active": "in active zone",
    "activation_uncertain": "activation unknown",
    "buffered_only": "near boundary",
}
_EXIT_WORDS = {
    "no_candidate": "nowhere near a zone",
    "outside_polygon": "near but outside a zone",
    "vertical_clear": "above or below a zone",
    "zone_inactive": "in an inactive zone",
    "on_ground": "on the ground",
    "bad_input": "no usable altitude",
}


def _clock(iso: Any) -> str:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).strftime("%H:%M:%SZ")
    except ValueError:
        return "unknown"


def _num(value: Any, digits: int = 3) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "?"


def render_text(report: Mapping[str, Any]) -> str:
    """Render ``report`` (from :func:`report.build_report`) for a terminal."""
    scope = report.get("scope") or {}
    feed = report.get("feed") or {}
    ev = report.get("evaluation") or {}
    det = report.get("detector") or {}
    lines = [
        "SkyWatch No-Fly-Zone Detector  (EXPERIMENTAL - not for navigation)",
        "",
        f"Area      {scope.get('name')} {scope.get('radiusNm')} NM around "
        f"{scope.get('lat')}, {scope.get('lon')}",
        f"Run       {_clock(report.get('generatedAt'))}",
        f"Feed      {feed.get('status')} via {feed.get('source') or 'unknown'}"
        f" ({feed.get('via') or '?'}), answer {_num(feed.get('snapshotAgeS'), 1)}s old, "
        f"{feed.get('count', '?')} aircraft",
        f"Detector  {det.get('id')} {det.get('version')}, "
        f"{det.get('baseline') or det.get('rulesVersion')}",
    ]
    if not ev.get("ran"):
        reason = ev.get("reason") or feed.get("reason") or "no reason given"
        lines += [
            "",
            f"Result    NOT EVALUATED: {reason}.",
            "          This is not the same as finding nothing.",
        ]
        return "\n".join(lines) + "\n"

    exits = ", ".join(
        f"{n} {_EXIT_WORDS.get(k, k)}"
        for k, n in sorted((ev.get("exits") or {}).items(), key=lambda kv: -kv[1])
    )
    skipped = ", ".join(
        f"{n} {k.replace('_', ' ')}" for k, n in (ev.get("skipped") or {}).items()
    )
    lines.append(f"Checked   {ev.get('statesEvaluated')} aircraft{': ' + exits if exits else ''}")
    if skipped:
        lines.append(f"Skipped   {skipped}")

    detections = report.get("detections") or []
    if not detections:
        lines += ["", "Result    No aircraft inside a zone volume."]
        return "\n".join(lines) + "\n"

    lines += [
        "",
        f"Detections ({len(detections)})",
        f"  {'CLASS':<19}{'SEV':<7}{'SCORE':<7}{'AIRCRAFT':<18}{'ZONE':<26}{'ALT FT':<9}"
        "OBSERVED (est.)",
    ]
    for d in detections:
        who = f"{d.get('aircraftId')}{' ' + d['callsign'] if d.get('callsign') else ''}"
        alt = d.get("altitudeFt")
        alt_text = (
            f"{round(alt)}{'b' if d.get('altitudeSource') == 'BAROMETRIC' else ''}"
            if isinstance(alt, (int, float))
            else "?"
        )
        cls = _CLASS_WORDS.get(str(d.get("classification")), str(d.get("classification")))
        lines.append(
            f"  {cls:<19}{d.get('severity')!s:<7}{_num(d.get('score')):<7}{who:<18}"
            f"{str(d.get('zoneName'))[:25]:<26}{alt_text:<9}{_clock(d.get('observedAt'))}"
        )
        s = d.get("scoring")
        if s:
            signals = ", ".join(
                f"{c['name']} {_num(c['weight'], 2)}" for c in s.get("contextSignals") or []
            )
            lines.append(
                f"      score = base {_num(s['base'])} ({s['baseReason']}) + depth "
                f"{_num(s['depthBump'])} ({_num(s['depthNm'], 2)} NM x {s['depthBumpPerNm']}, "
                f"cap {s['depthBumpCap']}) - context {_num(s['contextPenalty'])}"
                f"{' [' + signals + ']' if signals else ''} = {_num(s['score'])}"
            )
            lines += [f"      severity {cap}" for cap in s.get("severityCaps") or []]
        lines.append(f"      activation: {d.get('activationBasis')}")
    return "\n".join(lines) + "\n"
