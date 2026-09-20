"""Run the proximity detector on a fixture and print detections as JSON.

    python scripts/run_proximity.py air/fixtures/proximity_head_on.json

Thin on purpose: load, detect, print. No database, no network.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from air.detectors.proximity import ProximityDetector, load_config  # noqa: E402
from air.models.observation import AdsbObservation  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path, help="JSON list of AdsbObservation dicts")
    parser.add_argument("--config", type=Path, default=None, help="alternate proximity.yaml")
    args = parser.parse_args()

    rows = json.loads(args.fixture.read_text(encoding="utf-8"))
    observations = [AdsbObservation.from_dict(r) for r in rows]
    detector = ProximityDetector(load_config(args.config) if args.config else None)
    detections = detector.detect_observations(observations)

    print(json.dumps([d.to_dict() for d in detections], indent=2, default=str))
    print(f"\n{len(detections)} detection(s) from {len(observations)} observations", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
