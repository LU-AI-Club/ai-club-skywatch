"""Replay a readsb/tar1090 ADS-B CSV through the detectors, end to end.

A **no-database** way to see detectors work on real data: read the CSV, stream
it through the shared normalizer, slice it into epoch-anchored time windows, feed
each window to the selected detector(s), and print each emitted ``Detection`` as
JSON. This is the one-shot form of how detection runs on a live feed — there, the
same windowing logic runs on a timer over a rolling "last N minutes" slice.

Thin by design (the repo rule — streaming/feeds are enabling infra that *calls*
detectors, never baked inside them): all real logic lives in
``air/normalizers/adsb_csv.py`` and ``air/windowing.py``; this file only parses
args, wires them together, and emits output + a summary.

Run it (from the repo root)::

    python scripts/replay_csv.py                         # all available detectors, 60s tumbling
    python scripts/replay_csv.py --detector example_altitude --limit 5000
    python scripts/replay_csv.py --detector proximity --window 30 --step 10
    python scripts/replay_csv.py --out detections.jsonl --quiet

A detector that a team has not built yet is skipped with a note — the moment its
package exposes ``build_detector()`` (or a ``*Detector`` class), it lights up here
with no change to this script.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

# Allow `python scripts/replay_csv.py` from the repo root without installing:
# put the repo root (this file's parent's parent) on sys.path so `air`/`contracts`
# import. (pytest already does this via pyproject's pythonpath.)
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from air.normalizers.adsb_csv import NormalizationStats, iter_observations  # noqa: E402
from air.windowing import detection_dedup_key, iter_windows  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"

# name -> (module path, attribute). The attribute is a zero-arg detector factory
# OR a BaseDetector subclass with a zero-arg-friendly __init__. Teams: expose
# `build_detector()` in your package __init__ to appear here.
DETECTORS: dict[str, tuple[str, str]] = {
    "example_altitude": ("air.detectors._example_altitude.detector", "ExampleAltitudeDetector"),
    "spoofing": ("air.detectors.spoofing", "build_detector"),
    "proximity": ("air.detectors.proximity", "build_detector"),
    "no_fly_zone": ("air.detectors.no_fly_zone", "build_detector"),
}


def load_detector(name: str):
    """Return (detector, None) if it can be built, else (None, reason)."""
    module_path, attr = DETECTORS[name]
    try:
        module = importlib.import_module(module_path)
        factory = getattr(module, attr)
    except (ImportError, AttributeError):
        return None, f"{name}: not built yet (no {module_path}:{attr}) — skipped"
    try:
        detector = factory()  # class() instantiates; build_detector() constructs
    except Exception as exc:  # noqa: BLE001 - report, don't crash the whole run
        return None, f"{name}: failed to construct ({exc!r}) — skipped"
    if not hasattr(detector, "detect_observations"):
        return None, f"{name}: has no detect_observations() — skipped"
    return detector, None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV), help="readsb/tar1090 CSV (default: data/lynchburg_adsb.csv)")
    parser.add_argument("--detector", action="append", choices=sorted(DETECTORS), help="detector(s) to run; repeatable; default = all available")
    parser.add_argument("--window", type=float, default=60.0, help="window width in seconds (default: 60)")
    parser.add_argument("--step", type=float, default=None, help="window advance in seconds (default: = --window, i.e. tumbling; smaller = sliding)")
    parser.add_argument("--limit", type=int, default=None, help="cap observations (after time sort) for a quick smoke run")
    parser.add_argument("--max-windows", type=int, default=None, help="stop after this many windows")
    parser.add_argument("--receiver-id", default="lynchburg", help="receiver id stamped on observations (default: lynchburg)")
    parser.add_argument("--format", choices=("jsonl", "json"), default="jsonl", help="jsonl (one Detection per line) or json (one array)")
    parser.add_argument("--out", default=None, help="write detections to this file (default: stdout)")
    parser.add_argument("--quiet", action="store_true", help="suppress the summary printed to stderr")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    step = args.step if args.step is not None else args.window
    dedup = step < args.window  # overlapping windows would otherwise double-count

    # --- Build the requested detectors; skip (with a note) any not built yet.
    requested = args.detector or sorted(DETECTORS)
    detectors = []
    for name in requested:
        detector, reason = load_detector(name)
        if detector is None:
            print(reason, file=sys.stderr)
        else:
            detectors.append((name, detector))
    if not detectors:
        print("No runnable detectors. Build one, or pick --detector example_altitude.", file=sys.stderr)
        return 1

    # --- Normalize the CSV to observations (streaming), optionally capped.
    stats = NormalizationStats()
    observations = list(iter_observations(args.csv_path, receiver_id=args.receiver_id, stats=stats))
    if args.limit is not None:
        observations.sort(key=lambda o: o.observed_at)  # cap the *earliest* N for a stable slice
        observations = observations[: args.limit]

    # --- Replay through epoch-anchored windows into each detector.
    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    per_detector: Counter[str] = Counter()
    windows_seen = 0
    emitted = 0
    first_json = True
    seen_keys: set[tuple] = set()
    try:
        if args.format == "json":
            out.write("[")
        for window in iter_windows(observations, args.window, step):
            if args.max_windows is not None and windows_seen >= args.max_windows:
                break
            windows_seen += 1
            for name, detector in detectors:
                for detection in detector.detect_observations(window):
                    if dedup:
                        key = detection_dedup_key(detection)
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)
                    payload = json.dumps(detection.to_dict(), default=str)
                    if args.format == "json":
                        out.write(("" if first_json else ",") + "\n  " + payload)
                        first_json = False
                    else:
                        out.write(payload + "\n")
                    per_detector[name] += 1
                    emitted += 1
        if args.format == "json":
            out.write("\n]\n")
    finally:
        if out is not sys.stdout:
            out.close()

    if not args.quiet:
        print(
            f"\nnormalized {stats.normalized} obs (skipped {stats.skipped} of {stats.total_rows}); "
            f"{windows_seen} windows of {args.window:g}s (step {step:g}s{', dedup on' if dedup else ''}); "
            f"{emitted} detections.",
            file=sys.stderr,
        )
        for name, _ in detectors:
            print(f"  {name}: {per_detector[name]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
