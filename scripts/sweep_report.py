"""Measure what each threshold actually costs, instead of arguing about it.

Every limit in ``SpoofingConfig`` is currently a number someone reasoned to.
This sweeps each one across a range and records, at every value:

* how many alerts the real hour produces
* whether the guard fixtures still fire -- the gross misbehaviour that must
  be caught at any setting (``air/fixtures/spoofing/pos_guard_*.json``)
* whether the other positive fixtures still fire, and the negatives stay quiet

Then it names, per threshold, the value that produces the fewest alerts while
keeping every guard green. That recommendation is the point: it is the
difference between tuning and guessing.

The real hour is replayed exactly the way ``scripts/replay_csv.py`` replays
it -- same normalizer, same 60 s tumbling windows -- so the alert counts here
are the same numbers the team quotes elsewhere. Anything else would make this
report unusable for the question it exists to answer.

Usage (from the repo root)::

    python scripts/sweep_report.py
    python scripts/sweep_report.py --quick          # fewer values per threshold
    python scripts/sweep_report.py --only turn_rate_dps speed_delta_kt
    python scripts/sweep_report.py --out docs/spoofing/CALIBRATION_SWEEP.md

A full sweep replays the hour once per value and takes a few minutes. Use
``--only`` while iterating on one rule.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from air.detectors.spoofing.config import SpoofingConfig  # noqa: E402
from air.detectors.spoofing.detector import SpoofingDetector  # noqa: E402
from air.models.observation import AdsbObservation  # noqa: E402
from air.detectors.spoofing.reference import (  # noqa: E402
    load_faa_registry,
    load_icao_blocks,
)
from air.normalizers.adsb_csv import iter_observations  # noqa: E402
from air.windowing import iter_windows  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"
FIXTURES_DIR = REPO_ROOT / "air" / "fixtures" / "spoofing"
DEFAULT_OUT = REPO_ROOT / "docs" / "spoofing" / "CALIBRATION_SWEEP.md"

# The registry-mismatch rule does not run without reference data, so a sweep
# built on a bare detector would score its fixture as a permanent miss and
# report a rule we never exercised as safe to loosen.
REGISTRY_CSV = FIXTURES_DIR / "faa_registry_sample.csv"
ICAO_BLOCKS_CSV = FIXTURES_DIR / "icao_blocks_sample.csv"

# Match replay_csv.py's defaults, or the counts here mean nothing elsewhere.
WINDOW_S = 60.0
STEP_S = 60.0

# Which thresholds to sweep, and over what.
#
# Values run from tighter than today to looser. "Looser" is not always
# "larger": nic_floor and min_confidence loosen downward, so each entry says
# which direction reduces alerts, and the recommendation reads that way.
SWEEPS: dict[str, dict[str, Any]] = {
    "turn_rate_dps": {
        "values": [6.0, 8.0, 10.0, 15.0, 20.0, 30.0, 45.0],
        "quick": [10.0, 20.0, 30.0],
        "note": "Our largest single source of alerts.",
    },
    "speed_delta_kt": {
        "values": [25.0, 50.0, 75.0, 100.0, 150.0, 200.0],
        "quick": [50.0, 100.0, 150.0],
        "note": "Floor of the speed-disagreement limit.",
    },
    "speed_delta_frac": {
        "values": [0.15, 0.30, 0.45, 0.60, 0.80],
        "quick": [0.30, 0.50, 0.80],
        "note": "The limit is the larger of this share of reported speed and the floor.",
    },
    "vrate_delta_fpm": {
        "values": [1000.0, 2000.0, 4000.0, 6000.0, 9000.0, 12000.0],
        "quick": [2000.0, 6000.0, 12000.0],
        "note": "Measured disagreement on real traffic medians near 9,920 fpm.",
    },
    "position_error_m": {
        "values": [10.0, 30.0, 60.0, 100.0, 200.0],
        "quick": [30.0, 100.0, 200.0],
        "note": "Floor on each endpoint's position error; widens every speed allowance.",
    },
    "altitude_quantum_ft": {
        "values": [25.0, 50.0, 100.0, 200.0],
        "quick": [25.0, 100.0, 200.0],
        "note": "Altitude step size; sets the phantom climb rate at short gaps.",
    },
    "teleport_kt": {
        "values": [600.0, 800.0, 1000.0, 1500.0, 3000.0],
        "quick": [1000.0, 1500.0, 3000.0],
        "note": "Already quiet on this hour; swept to prove the guard holds.",
    },
    "min_dt_s": {
        "values": [0.5, 1.0, 2.0, 3.0, 5.0],
        "quick": [0.5, 2.0, 5.0],
        "note": "Pairs closer together than this are not measured at all.",
    },
    "min_confidence": {
        "values": [0.2, 0.35, 0.5, 0.65, 0.8],
        "quick": [0.35, 0.6, 0.8],
        "note": "Alerts below this confidence are suppressed. Raising it is the blunt lever.",
    },
    "min_segment_observations": {
        "values": [2, 3, 5, 8, 12],
        "quick": [3, 8, 12],
        "note": "Segments shorter than this are too thin to judge.",
    },
}


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def load_fixtures() -> list[dict[str, Any]]:
    """Read every fixture once, with its expected outcome.

    Reading these per sweep value would dominate the runtime and tell us
    nothing new -- the files do not change while the sweep runs.
    """
    loaded: list[dict[str, Any]] = []
    for path in sorted(FIXTURES_DIR.glob("*.json")):
        rows = json.loads(path.read_text(encoding="utf-8"))

        expected_positive = False
        expected_gate = "unlabeled"
        for row in rows:
            kind, _, gate = row.get("_label", "").partition(":")
            if kind == "positive":
                expected_positive = True
                expected_gate = gate or "unlabeled"
                break
            if kind == "negative":
                expected_gate = gate or "unlabeled"

        loaded.append(
            {
                "name": path.name,
                "is_guard": path.name.startswith("pos_guard_"),
                "expected_positive": expected_positive,
                "expected_gate": expected_gate,
                "observations": [AdsbObservation.from_dict(row) for row in rows],
            }
        )
    return loaded


def score_fixtures(detector, fixtures: list[dict[str, Any]]) -> dict[str, Any]:
    """How this detector does on the fixture set.

    ``guards_held`` is the one that decides a recommendation. The rest is
    context: a setting can keep every guard green and still break ordinary
    positives, and the table should show that rather than hide it.
    """
    guards_total = guards_held = 0
    positives_total = positives_fired = 0
    negatives_total = negatives_quiet = 0
    missed_guards: list[str] = []

    for fixture in fixtures:
        detections = detector.detect_observations(fixture["observations"])
        gates = {d.metadata.get("gate") for d in detections}

        if fixture["expected_positive"]:
            fired = fixture["expected_gate"] in gates
            positives_total += 1
            positives_fired += int(fired)
            if fixture["is_guard"]:
                guards_total += 1
                guards_held += int(fired)
                if not fired:
                    missed_guards.append(fixture["name"])
        else:
            negatives_total += 1
            negatives_quiet += int(not detections)

    return {
        "guards_held": guards_held,
        "guards_total": guards_total,
        "positives_fired": positives_fired,
        "positives_total": positives_total,
        "negatives_quiet": negatives_quiet,
        "negatives_total": negatives_total,
        "missed_guards": missed_guards,
    }


# --------------------------------------------------------------------------
# the real hour
# --------------------------------------------------------------------------
def load_windows(csv_path: Path) -> list[list[AdsbObservation]]:
    """Slice the capture the same way replay_csv.py does, once."""
    observations = list(iter_observations(csv_path))
    return list(iter_windows(observations, WINDOW_S, STEP_S))


def count_real_alerts(detector, windows) -> int:
    return sum(len(detector.detect_observations(window)) for window in windows)


# --------------------------------------------------------------------------
# sweeping
# --------------------------------------------------------------------------
def sweep_setting(
    setting: str,
    values: list[Any],
    windows,
    fixtures,
    baseline: SpoofingConfig,
    reference: dict[str, Any],
) -> list[dict[str, Any]]:
    """One row per value: alerts on the real hour, plus fixture outcomes.

    The detector is rebuilt for each measurement rather than reused. Several
    rules carry state across calls, and a detector that has already seen the
    real hour does not judge a fixture the same way a fresh one does.
    """
    rows: list[dict[str, Any]] = []
    for value in values:
        cfg = dataclasses.replace(baseline, **{setting: value})

        started = time.time()
        row: dict[str, Any] = {
            "setting": setting,
            "value": value,
            "alerts": count_real_alerts(
                SpoofingDetector(config=cfg, **reference), windows
            ),
        }
        row.update(
            score_fixtures(SpoofingDetector(config=cfg, **reference), fixtures)
        )
        row["seconds"] = round(time.time() - started, 1)
        rows.append(row)
        print(
            f"  {setting}={value!r:>8}  alerts={row['alerts']:<5} "
            f"guards={row['guards_held']}/{row['guards_total']}  "
            f"pos={row['positives_fired']}/{row['positives_total']}  "
            f"neg={row['negatives_quiet']}/{row['negatives_total']}  "
            f"({row['seconds']}s)",
            flush=True,
        )
    return rows


def recommend(
    rows: list[dict[str, Any]], current: Any
) -> tuple[dict[str, Any] | None, bool]:
    """Fewest alerts among values that cost us nothing we can see.

    Two conditions, in order. Every guard must still fire -- that is the
    floor, and a value that breaks it is not a candidate however quiet it
    is. Then the ordinary positives must not regress below what the current
    setting already catches: a value can hold every guard and still stop
    detecting half the planted cases, and recommending that would be worse
    than recommending nothing.

    Returns the row and whether it had to fall back to guards-only because
    no value cleared both bars. Ties go to the tightest value tried, since
    when two settings cost the same we should give away less.
    """
    safe = [r for r in rows if r["guards_held"] == r["guards_total"]]
    if not safe:
        return None, False

    at_current = next((r for r in rows if r["value"] == current), None)
    floor = at_current["positives_fired"] if at_current else 0
    no_regression = [r for r in safe if r["positives_fired"] >= floor]

    pool, relaxed = (no_regression, False) if no_regression else (safe, True)
    return min(pool, key=lambda r: (r["alerts"], rows.index(r))), relaxed


# --------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------
def render(all_rows: dict[str, list[dict[str, Any]]], baseline: SpoofingConfig) -> str:
    out: list[str] = []
    out.append("# Spoofing — Threshold Sweep")
    out.append("")
    out.append(
        "Generated by `python scripts/sweep_report.py`. Do not hand-edit; "
        "re-run it instead."
    )
    out.append("")
    out.append(
        f"Each row replays `data/lynchburg_adsb.csv` through {WINDOW_S:g}s tumbling "
        f"windows, exactly as `scripts/replay_csv.py` does, with one threshold "
        f"changed and everything else at its current value."
    )
    out.append("")
    out.append(
        "**Guards** are `pos_guard_*.json` — gross misbehaviour that must be "
        "caught at any setting. A value that drops a guard is not a candidate, "
        "however few alerts it produces."
    )
    out.append("")

    out.append("## Recommended values")
    out.append("")
    out.append("| Threshold | Current | Recommended | Alerts | vs current | Positives |")
    out.append("|---|---:|---:|---:|---:|---:|")
    relaxed_any = False
    for setting, rows in all_rows.items():
        current = getattr(baseline, setting)
        best, relaxed = recommend(rows, current)
        at_current = next((r for r in rows if r["value"] == current), None)
        if best is None:
            out.append(
                f"| `{setting}` | {current} | **no safe value in range** | — | — | — |"
            )
            continue
        relaxed_any = relaxed_any or relaxed
        delta = (
            f"{best['alerts'] - at_current['alerts']:+d}"
            if at_current is not None
            else "—"
        )
        mark = "" if best["value"] == current else "**"
        warn = " ⚠" if relaxed else ""
        out.append(
            f"| `{setting}` | {current} | {mark}{best['value']}{mark}{warn} "
            f"| {best['alerts']} | {delta} "
            f"| {best['positives_fired']}/{best['positives_total']} |"
        )
    out.append("")
    out.append(
        "A recommendation is the fewest alerts among values that keep every "
        "guard firing **and** catch at least as many ordinary positives as "
        "the current setting does. It is still a measurement, not a "
        "decision — read the per-threshold table before taking one."
    )
    if relaxed_any:
        out.append("")
        out.append(
            "⚠ marks a threshold where no value cleared both bars, so the "
            "recommendation holds the guards but catches fewer ordinary "
            "positives than today. Treat those as findings to investigate, "
            "not values to adopt."
        )
    out.append("")

    for setting, rows in all_rows.items():
        meta = SWEEPS[setting]
        current = getattr(baseline, setting)
        out.append(f"## `{setting}`")
        out.append("")
        out.append(meta["note"])
        out.append("")
        out.append("| Value | Alerts/hour | Guards | Positives | Negatives quiet |")
        out.append("|---:|---:|---:|---:|---:|")
        for row in rows:
            flag = " ← current" if row["value"] == current else ""
            guards = f"{row['guards_held']}/{row['guards_total']}"
            if row["guards_held"] < row["guards_total"]:
                guards = f"**{guards}**"
            out.append(
                f"| {row['value']}{flag} | {row['alerts']} | {guards} "
                f"| {row['positives_fired']}/{row['positives_total']} "
                f"| {row['negatives_quiet']}/{row['negatives_total']} |"
            )
        out.append("")
        broken = [r for r in rows if r["missed_guards"]]
        if broken:
            out.append("Guards lost:")
            out.append("")
            for row in broken:
                out.append(f"- `{row['value']}` → {', '.join(row['missed_guards'])}")
            out.append("")

    return "\n".join(out) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="three values per threshold instead of the full range",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        metavar="SETTING",
        help="sweep only these thresholds",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    settings = list(SWEEPS)
    if args.only:
        unknown = [s for s in args.only if s not in SWEEPS]
        if unknown:
            print(f"Not sweepable: {', '.join(unknown)}", file=sys.stderr)
            print(f"Known: {', '.join(SWEEPS)}", file=sys.stderr)
            return 1
        settings = args.only

    baseline = SpoofingConfig()
    reference = {
        "registry": load_faa_registry(REGISTRY_CSV),
        "icao_blocks": load_icao_blocks(ICAO_BLOCKS_CSV),
    }

    print(f"Loading {args.csv} ...", flush=True)
    windows = load_windows(args.csv)
    fixtures = load_fixtures()
    guards = sum(1 for f in fixtures if f["is_guard"])
    print(
        f"{len(windows)} windows, {len(fixtures)} fixtures ({guards} guards)",
        flush=True,
    )

    all_rows: dict[str, list[dict[str, Any]]] = {}
    for setting in settings:
        values = SWEEPS[setting]["quick" if args.quick else "values"]
        print(f"\n{setting}:", flush=True)
        all_rows[setting] = sweep_setting(
            setting, values, windows, fixtures, baseline, reference
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(all_rows, baseline), encoding="utf-8")

    # A full sweep costs minutes. Keep the measurements so the table can be
    # reshaped later without paying for them again.
    rows_path = args.out.with_suffix(".json")
    rows_path.write_text(json.dumps(all_rows, indent=2) + "\n", encoding="utf-8")

    try:
        shown = args.out.relative_to(REPO_ROOT)
    except ValueError:  # --out pointed outside the repo
        shown = args.out
    print(f"\nWrote {shown} (+ {rows_path.name})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
