"""Evaluation harness for the spoofing detector.

No database, no network: everything here is plain functions over fixture
files and in-memory objects, per docs/DETECTOR_PLAYBOOK.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from air.models.observation import AdsbObservation


def run_on_fixtures(detector, fixture_folder: str | Path) -> list[dict]:
    """Run `detector` over every fixture JSON file in `fixture_folder`.

    `detector` can be anything with a `.detect_observations(observations) ->
    detections` method — no real spoofing detector exists yet, so this is
    tested against a hand-built fake one (see tests/air/detectors/spoofing/test_spoofing_run_on_fixtures.py).

    Returns one dict per fixture file:
        fixture_name       - the file name
        expected_positive  - should this fixture have produced a detection?
        expected_gate      - which rule it should have tripped
        detections         - what the detector actually returned
        fired               - True if the detector returned anything

    `expected_positive` / `expected_gate` come from each row's `_label`
    annotation (`"positive:<gate>"` or `"negative:<gate>"` or `"ok"`) — see
    air/fixtures/spoofing/README.md. Fixtures label only the specific rows a
    positive case touches (the rest stay `"ok"`), so a `"positive:..."` tag
    anywhere in the file wins over everything else.
    """
    folder = Path(fixture_folder)
    results: list[dict] = []

    for path in sorted(folder.glob("*.json")):
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

        observations = [AdsbObservation.from_dict(row) for row in rows]
        detections = detector.detect_observations(observations)

        results.append(
            {
                "fixture_name": path.name,
                "expected_positive": expected_positive,
                "expected_gate": expected_gate,
                "detections": detections,
                "fired": len(detections) > 0,
            }
        )

    return results


def confusion_counts(results: list[dict]) -> dict[str, dict[str, int]]:
    """Count catches, false alarms and misses per rule.

    `results` is the list `run_on_fixtures` returns. Each result is filed
    under its `expected_gate` and lands in exactly one of four boxes:

        tp - catch:        should have fired, and did
        fn - miss:         should have fired, and did not
        fp - false alarm:  should not have fired, but did
        tn - correct quiet: should not have fired, and did not

    Returns one dict of those four counts per rule, e.g.
        {"teleport_v1": {"tp": 1, "fp": 0, "fn": 0, "tn": 1}}
    """
    counts: dict[str, dict[str, int]] = {}

    for result in results:
        gate = result["expected_gate"]
        if gate not in counts:
            counts[gate] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}

        if result["expected_positive"] and result["fired"]:
            counts[gate]["tp"] += 1
        elif result["expected_positive"]:
            counts[gate]["fn"] += 1
        elif result["fired"]:
            counts[gate]["fp"] += 1
        else:
            counts[gate]["tn"] += 1

    return counts


def precision_recall(counts: dict[str, int]) -> tuple[float | None, float | None]:
    """Turn one rule's counts into (precision, recall).

    `counts` is one rule's dict from `confusion_counts`, e.g.
    `confusion_counts(results)["teleport_v1"]`. Only `tp`, `fp` and `fn` are
    read.

        precision - of what we flagged, how much was right:   tp / (tp + fp)
        recall    - of what we planted, how much we caught:   tp / (tp + fn)

    Both are between 0.0 and 1.0. If nothing was flagged, precision has
    nothing to divide by and is None; if nothing was planted, recall is None.
    """
    tp = counts["tp"]
    fp = counts["fp"]
    fn = counts["fn"]

    flagged = tp + fp
    planted = tp + fn

    precision = tp / flagged if flagged > 0 else None
    recall = tp / planted if planted > 0 else None

    return precision, recall


__all__ = ["run_on_fixtures", "confusion_counts", "precision_recall"]
