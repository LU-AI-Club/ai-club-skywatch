"""Summarize spoofing-detector alerts from the Lynchburg ADS-B capture.

Run from the repository root::

    python scripts/alert_breakdown.py
    python scripts/alert_breakdown.py --out alert-breakdown.md
    python scripts/alert_breakdown.py --window 300        # 5-minute windows

This is the *report* over the same run ``scripts/replay_csv.py`` performs, and
it must agree with it: both feed the capture through the shared normalizer in
60-second epoch-anchored windows, deduplicating findings across window
overlaps. replay_csv emits the detections; this script counts them.

That agreement is the whole point, and it was previously missing. This script
used to hand the detector all 284,476 observations in one call, which reported
**160** alerts against replay_csv's **52**. The gap was not a tuning
disagreement -- it was an artifact of the measurement:

* **No windowing.** Every physics rule here compares *consecutive* reports of
  one aircraft. Unwindowed, consecutive means consecutive in the whole file, so
  a pair can straddle a ten-minute gap in coverage: an aircraft leaves range
  over Roanoke and the next report of it is near Richmond, which reads as an
  impossible jump. Windowing is not a performance detail, it is part of what
  the rules mean, and live the detector only ever sees a window.
* **The wrong normalizer.** It read ``air/normalizers/lynchburg_csv.py``, the
  week-1 spoofing-only reader, rather than the shared
  ``air/normalizers/adsb_csv.py`` that replay_csv, the database loader and the
  live reader all use. Two normalizers over one file disagree about which rows
  survive, so the two scripts were not even summarizing the same observations.

A number quoted from here is quoted as the detector's alert count, so it has to
be the number the live path would produce. Keep this script and replay_csv on
the same normalizer, the same windows and the same dedup.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from air.detectors.spoofing import build_detector  # noqa: E402
from air.normalizers.adsb_csv import iter_observations  # noqa: E402
from air.windowing import detection_dedup_key, iter_windows  # noqa: E402
from contracts import Detection  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"

# Defaults chosen to match scripts/replay_csv.py, not independently: these two
# scripts reporting different numbers for one capture is the bug this file was
# fixed for.
DEFAULT_WINDOW_S = 60.0
DEFAULT_RECEIVER_ID = "lynchburg"


@dataclass
class RuleStats:
    alerts: int = 0
    dt_s: list[float] = field(default_factory=list)
    reported_speeds_kt: list[float] = field(default_factory=list)
    measured_values: list[float] = field(default_factory=list)
    measured_units: set[str] = field(default_factory=set)


def _append_number(values: list[float], value: Any) -> None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        values.append(float(value))


def _format_median(values: list[float], unit: str | None = None) -> str:
    if not values:
        return "N/A"
    value = f"{median(values):.2f}"
    return f"{value} {unit}" if unit else value


def build_report(detections: list[Detection]) -> str:
    """Render alert totals and per-rule/per-severity summaries as Markdown."""
    rules: defaultdict[str, RuleStats] = defaultdict(RuleStats)
    severities: Counter[str] = Counter()

    for detection in detections:
        gate = detection.metadata["gate"]
        event = detection.metadata["event"]
        if not isinstance(gate, str):
            raise ValueError(f"Detection has an invalid rule name: {gate!r}")

        stats = rules[gate]
        stats.alerts += 1
        _append_number(stats.measured_values, event.get("measured"))
        unit = event.get("unit")
        if isinstance(unit, str):
            stats.measured_units.add(unit)

        for evidence in detection.evidence:
            if evidence.evidence_type != "kinematic_pair":
                continue
            _append_number(stats.dt_s, evidence.metadata.get("dt_s"))
            _append_number(
                stats.reported_speeds_kt,
                evidence.metadata.get("reported_speed_kt"),
            )

        severity = detection.severity.value
        severities[severity] += 1

    lines = [
        "# Alert breakdown",
        "",
        f"- Total alerts: **{len(detections)}**",
        "",
        "## Alerts by rule",
        "",
        "| Rule | Alerts | Median dt_s (s) | Median reported speed (kt) | Median measured value |",
        "|---|---:|---:|---:|---:|",
    ]

    for gate, stats in sorted(rules.items(), key=lambda item: (-item[1].alerts, item[0])):
        unit = ", ".join(sorted(stats.measured_units)) or None
        lines.append(
            f"| {gate} | {stats.alerts} "
            f"| {_format_median(stats.dt_s)} "
            f"| {_format_median(stats.reported_speeds_kt)} "
            f"| {_format_median(stats.measured_values, unit)} |"
        )
    if not rules:
        lines.append("| (none) | 0 | N/A | N/A | N/A |")

    lines.extend(
        [
            "",
            "## Alerts by severity",
            "",
            "| Severity | Alerts |",
            "|---|---:|",
        ]
    )
    for severity, count in sorted(severities.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"| {severity} | {count} |")
    if not severities:
        lines.append("| (none) | 0 |")

    return "\n".join(lines) + "\n"


def collect_detections(
    observations: list[Any],
    *,
    window_s: float,
    step_s: float | None,
) -> list[Detection]:
    """Run the detector the way the live path does: window by window.

    Mirrors the loop in ``scripts/replay_csv.py``. Overlapping windows (a
    ``step_s`` below ``window_s``) hand the detector the same pair more than
    once, so findings are deduplicated on ``detection_dedup_key`` -- the same
    key the database upserts on, which is what keeps a rolling live runner from
    piling up one finding per tick.
    """
    detector = build_detector()
    detections: list[Detection] = []
    seen: set[Any] = set()
    for window in iter_windows(observations, window_s, step_s):
        for detection in detector.detect_observations(window):
            key = detection_dedup_key(detection)
            if key in seen:
                continue
            seen.add(key)
            detections.append(detection)
    return detections


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        help="also write the Markdown report to this file",
    )
    parser.add_argument(
        "--window",
        type=float,
        default=DEFAULT_WINDOW_S,
        help=f"window width in seconds (default: {DEFAULT_WINDOW_S:g}, matching replay_csv.py)",
    )
    parser.add_argument(
        "--step",
        type=float,
        default=None,
        help="window advance in seconds (default: = --window, i.e. tumbling)",
    )
    args = parser.parse_args(argv)

    observations = list(iter_observations(DEFAULT_CSV, receiver_id=DEFAULT_RECEIVER_ID))
    detections = collect_detections(
        observations, window_s=args.window, step_s=args.step
    )
    report = build_report(detections)

    print(report, end="")
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
