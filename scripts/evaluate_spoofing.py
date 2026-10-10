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


def sweep_threshold(
    setting: str,
    values: list[float],
    fixture_folder: str | Path,
    make_detector,
) -> list[dict]:
    """Try one limit at many values and score the detector at each one.

    `setting` is the name of the limit to change (e.g. `"teleport_kt"`) and
    `values` are the numbers to try for it.

    `make_detector` is a function that takes a dict of settings, e.g.
    `{"teleport_kt": 800}`, and returns a detector built with them. No real
    spoofing detector exists yet, so the caller has to say how to build one
    (see tests/air/detectors/spoofing/test_spoofing_sweep_threshold.py for a
    hand-built fake).

    Returns the table as a list of dicts, one row per value, in the order
    the values were given:
        setting    - the name of the limit
        value      - the value tried on this row
        tp, fp, fn, tn - counts added up across every rule
        precision  - from those totals, or None if nothing was flagged
        recall     - from those totals, or None if nothing was planted
    """
    table: list[dict] = []

    for value in values:
        detector = make_detector({setting: value})
        results = run_on_fixtures(detector, fixture_folder)

        totals = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
        for gate_counts in confusion_counts(results).values():
            for box in totals:
                totals[box] += gate_counts[box]

        precision, recall = precision_recall(totals)

        table.append(
            {
                "setting": setting,
                "value": value,
                "tp": totals["tp"],
                "fp": totals["fp"],
                "fn": totals["fn"],
                "tn": totals["tn"],
                "precision": precision,
                "recall": recall,
            }
        )

    return table


def implied_speed_histogram(
    records,
    teleport_kt: float = 1000.0,
    bin_width_kt: float = 50.0,
    max_kt: float = 2000.0,
):
    """Chart how many feature records fall at each implied speed.

    `records` is a list of `SpoofingFeatureRecord` (anything with an
    `implied_speed_kt` attribute works). Real aircraft pile up on the left,
    impossible jumps land far to the right, and the teleport limit belongs
    in the empty space between them. A dashed line marks `teleport_kt` so
    you can see whether it sits in that space.

    Speeds are grouped into bars `bin_width_kt` wide from 0 up to `max_kt`.
    Anything at or above `max_kt` goes in one last bar, so a single 34,000 kt
    jump does not squash everything else. The count axis is a log scale so a
    bar of 1 is still visible next to a bar of hundreds.

    Returns a matplotlib `Figure` (save it with `fig.savefig("chart.png")`),
    or None if no record has an implied speed. Records whose
    `implied_speed_kt` is None are left out.

    Needs matplotlib, which is in the `eda` extras: `pip install ".[eda]"`.
    """
    # Imported here, not at the top, so the rest of this file still works
    # for teammates who only installed the dev extras.
    from matplotlib.figure import Figure

    speeds = [r.implied_speed_kt for r in records if r.implied_speed_kt is not None]
    if not speeds:
        return None

    n_bins = int(max_kt // bin_width_kt)
    counts = [0] * (n_bins + 1)  # the extra bar at the end is "max_kt or faster"
    for speed in speeds:
        index = min(int(speed // bin_width_kt), n_bins)
        counts[index] += 1

    left_edges = [i * bin_width_kt for i in range(n_bins + 1)]

    ink = "#0b0b0b"
    muted = "#52514e"
    surface = "#fcfcfb"

    fig = Figure(figsize=(9, 4.5), facecolor=surface)
    ax = fig.subplots()
    ax.set_facecolor(surface)

    ax.bar(left_edges, counts, width=bin_width_kt * 0.9, align="edge", color="#2a78d6")
    ax.axvline(teleport_kt, color=ink, linestyle="--", linewidth=1.5)
    ax.annotate(
        f"teleport limit: {teleport_kt:g} kt",
        xy=(teleport_kt, 1),
        xycoords=("data", "axes fraction"),
        xytext=(6, -6),
        textcoords="offset points",
        ha="left",
        va="top",
        color=ink,
    )

    ax.set_yscale("log")
    ax.set_ylim(bottom=0.5)
    ax.set_xlim(0, max_kt + bin_width_kt)
    ticks = [max_kt * i / 4 for i in range(5)]
    ax.set_xticks(ticks)
    ax.set_xticklabels([f"{t:g}" for t in ticks[:-1]] + [f"{max_kt:g}+"])

    ax.set_title("Implied speed between consecutive reports", color=ink, loc="left")
    ax.set_xlabel("Implied speed (kt)", color=muted)
    ax.set_ylabel("Feature records (log scale)", color=muted)
    ax.tick_params(colors=muted)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(muted)

    fig.tight_layout()
    return fig


__all__ = [
    "run_on_fixtures",
    "confusion_counts",
    "precision_recall",
    "sweep_threshold",
    "implied_speed_histogram",
]
