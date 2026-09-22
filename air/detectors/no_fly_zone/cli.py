"""Stream H - the command-line harness.

    python -m air.detectors.no_fly_zone run --input FILE --out DIR

Unlike the stage modules this one is IMPLEMENTED, and deliberately so: it is
the scaffold every other stream develops against. It runs each stage in order,
catches :class:`NotImplementedError` from the ones nobody has written yet, and
prints a status line per stage. So an owner can run the whole pipeline on day
one, see their stage marked TODO, fill it in, and watch it flip to ok.

Inputs
------
--input
    ADS-B file for stream A (CSV or Parquet).
--out
    Output directory. ``detections.jsonl`` is written here, one detection per
    line. Lines are the **platform** contract (``contracts.Detection``),
    converted by :func:`emit.to_platform_detection` - that is what makes
    Week-11 TCE/CAATS integration wiring rather than a rewrite.
--airspace
    Zone GeoJSON. Defaults to ``airspace.fixture_path`` from config.
--config
    Config file. Defaults to the packaged ``config/config.yaml``.

Exit codes
----------
0
    Every stage ran.
1
    At least one stage is still NotImplementedError.
2
    A stage raised a real error (bad file, bad config).

Notes
-----
Unlike the stage modules, this one may import from every stage - it is wiring,
not logic. Keep it that way: if you find yourself deciding something here, it
belongs in a stage module.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import DEFAULT_PATH, load_config

_STAGE_OK = "ok"
_STAGE_TODO = "TODO"
_STAGE_FAIL = "FAIL"


def _report(stage: str, status: str, detail: str = "") -> None:
    """Print one aligned status line."""
    print(f"  {stage:<22} {status:<5} {detail}".rstrip())


def run(
    input_path: Path, out_dir: Path, airspace_path: Path | None, config_path: Path
) -> int:
    """Run the pipeline, reporting each stage. Returns a process exit code."""
    todo = 0
    print(f"no_fly_zone: {input_path}")

    try:
        cfg = load_config(config_path)
    except Exception as exc:  # noqa: BLE001 - a harness must survive any stage failure
        _report("config", _STAGE_FAIL, f"{type(exc).__name__}: {exc}")
        return 2
    _report("config", _STAGE_OK, f"baseline={cfg.baseline_version}")

    if airspace_path is None:
        configured = Path(cfg["airspace"]["fixture_path"])
        # Config paths are relative to the package, not the caller's cwd, so the
        # CLI behaves the same no matter which directory it is invoked from.
        airspace_path = (
            configured
            if configured.is_absolute()
            else Path(__file__).resolve().parent / configured
        )

    # Stage B - zones.
    zones: list[Any] = []
    try:
        from .ingest.airspace_loader import load_zones

        zones = load_zones(airspace_path)
        _report("B airspace_loader", _STAGE_OK, f"{len(zones)} zones")
    except NotImplementedError as exc:
        todo += 1
        _report("B airspace_loader", _STAGE_TODO, str(exc))
    except Exception as exc:  # noqa: BLE001 - report the stage, do not crash the run
        _report("B airspace_loader", _STAGE_FAIL, f"{type(exc).__name__}: {exc}")
        return 2

    # Stage A - states.
    states: list[Any] = []
    try:
        from .ingest.adsb_loader import load_states

        states = list(load_states(input_path))
        _report("A adsb_loader", _STAGE_OK, f"{len(states)} states")
    except NotImplementedError as exc:
        todo += 1
        _report("A adsb_loader", _STAGE_TODO, str(exc))
    except Exception as exc:  # noqa: BLE001 - report the stage, do not crash the run
        _report("A adsb_loader", _STAGE_FAIL, f"{type(exc).__name__}: {exc}")
        return 2

    # Stages C-G, wired by the lead.
    detections: list[Any] = []
    try:
        from .logic.detector import run as run_pipeline

        detections = list(run_pipeline(states, zones, cfg))
        _report("C-G pipeline", _STAGE_OK, f"{len(detections)} detections")
    except NotImplementedError as exc:
        todo += 1
        _report("C-G pipeline", _STAGE_TODO, str(exc))
    except Exception as exc:  # noqa: BLE001 - report the stage, do not crash the run
        _report("C-G pipeline", _STAGE_FAIL, f"{type(exc).__name__}: {exc}")
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "detections.jsonl"
    try:
        from .emit import to_platform_detection

        lines = [
            json.dumps(to_platform_detection(det).to_dict()) + "\n"
            for det in detections
        ]
    except ValueError as exc:
        # Stream G left a required extras key out. Say so plainly: a detection
        # we cannot place in time or space is not one we should write.
        _report("output", _STAGE_FAIL, f"cannot emit platform contract: {exc}")
        return 2
    with open(out_file, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    _report("output", _STAGE_OK, f"{out_file} ({len(lines)} detections)")

    if todo:
        print(f"\n{todo} stage(s) not implemented yet - see the table in CLAUDE.md")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (separate so tests can exercise it)."""
    parser = argparse.ArgumentParser(prog="no_fly_zone")
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run", help="run the detector over a recorded file")
    runner.add_argument("--input", required=True, type=Path)
    runner.add_argument("--out", required=True, type=Path)
    runner.add_argument("--airspace", type=Path, default=None)
    runner.add_argument("--config", type=Path, default=DEFAULT_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns an exit code rather than calling sys.exit."""
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return run(args.input, args.out, args.airspace, args.config)
    return 2


if __name__ == "__main__":
    sys.exit(main())
