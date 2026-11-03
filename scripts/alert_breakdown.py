"""Summarize spoofing-detector alerts from the Lynchburg ADS-B capture.

Run from the repository root::

    python scripts/alert_breakdown.py
    python scripts/alert_breakdown.py --out alert-breakdown.md
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
from air.normalizers.lynchburg_csv import load_csv  # noqa: E402
from contracts import Detection  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        help="also write the Markdown report to this file",
    )
    args = parser.parse_args(argv)

    observations = load_csv(DEFAULT_CSV)
    detections = build_detector().detect_observations(observations)
    report = build_report(detections)

    print(report, end="")
    if args.out:
        args.out.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
