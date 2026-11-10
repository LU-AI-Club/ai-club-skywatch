"""Generic live-runner entry point — the command every runner container runs.

One image, one script, every detector: ``--detector {spoofing,proximity,no_fly_zone}``
selects which one. The compose runner services pass different ``--detector``
values (and may override the window/step/poll). This is **Tech-Lead-owned
scaffolding**: it wires the CLI/env to ``air.live.run_live``. The detector logic,
the observations reader, the persistence layer, and ``run_live`` itself are built
by the teams (see ``docs/live_integration/``).

Until the spine bodies in ``air/live/`` are implemented, this exits with
``NotImplementedError`` naming the owning team — that is expected. The image and
compose wiring are ready for when A, B and C land.

Run:
    python scripts/run_live_detector.py --detector proximity --once
    python scripts/run_live_detector.py --detector spoofing          # polls forever
    python scripts/run_live_detector.py --detector no_fly_zone --window-s 600
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Allow `python scripts/run_live_detector.py` from the repo root without
# installing the package (mirrors scripts/replay_csv.py).
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from air.live import run_live  # noqa: E402


@dataclass(frozen=True)
class RunnerSpec:
    """Per-detector defaults. Window/step/poll follow SPINE_PLAN.md and are
    tunable with the flags below; the table name is fixed by the Tech Lead."""

    module: str          # detector package exposing a zero-arg build_detector()
    factory: str
    table: str
    window_s: float
    step_s: float
    poll_interval_s: float


RUNNERS: dict[str, RunnerSpec] = {
    "spoofing": RunnerSpec(
        "air.detectors.spoofing", "build_detector", "spoofing_detections",
        window_s=3600, step_s=300, poll_interval_s=300,
    ),
    "proximity": RunnerSpec(
        "air.detectors.proximity", "build_detector", "proximity_detections",
        window_s=120, step_s=30, poll_interval_s=30,
    ),
    "no_fly_zone": RunnerSpec(
        # build_live_detector: also emits incursions still in progress (OPEN),
        # so a row appears on entry and is upserted in place until exit.
        "air.detectors.no_fly_zone", "build_live_detector", "no_fly_zone_detections",
        window_s=300, step_s=30, poll_interval_s=30,
    ),
}

DEFAULT_DSN = os.environ.get(
    "SKYWATCH_DB_DSN", "postgresql://skywatch:skywatch@localhost:5432/skywatch"
)


def build_detector(spec: RunnerSpec):
    """Instantiate the detector via its package's ``build_detector()``."""
    module = importlib.import_module(spec.module)
    return getattr(module, spec.factory)()


def load_extra_columns(name: str):
    """Optional per-team column mapper at ``air.detectors.<name>.live.extra_columns``.

    Each team adds its own ``live.py`` with an ``extra_columns(detection) -> dict``
    (its detector-specific flattened columns). Absent is fine — the shared
    columns are filled by the persistence layer regardless. This keeps teams from
    editing this shared script.
    """
    try:
        module = importlib.import_module(f"air.detectors.{name}.live")
    except ModuleNotFoundError:
        return None
    return getattr(module, "extra_columns", None)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--detector", required=True, choices=sorted(RUNNERS))
    parser.add_argument("--dsn", default=DEFAULT_DSN, help=f"Postgres DSN (default: {DEFAULT_DSN})")
    parser.add_argument("--window-s", type=float, default=None, help="override rolling lookback W")
    parser.add_argument("--step-s", type=float, default=None, help="override cursor step")
    parser.add_argument("--poll-interval-s", type=float, default=None, help="override sleep between ticks")
    parser.add_argument("--startup-delay-s", type=float, default=0.0, help="sleep before the first run")
    parser.add_argument("--once", action="store_true", help="run a single tick and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # The runner logs one line per tick; without a handler only warnings
    # would reach `docker logs`.
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    spec = RUNNERS[args.detector]
    window_s = spec.window_s if args.window_s is None else args.window_s
    step_s = spec.step_s if args.step_s is None else args.step_s
    poll_interval_s = spec.poll_interval_s if args.poll_interval_s is None else args.poll_interval_s

    detector = build_detector(spec)
    extra_columns = load_extra_columns(args.detector)

    if args.startup_delay_s > 0:
        print(f"waiting {args.startup_delay_s:g}s before first run", file=sys.stderr)
        time.sleep(args.startup_delay_s)

    run_live(
        detector=detector,
        table=spec.table,
        dsn=args.dsn,
        window_s=window_s,
        step_s=step_s,
        poll_interval_s=poll_interval_s,
        extra_columns=extra_columns,
        once=args.once,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
