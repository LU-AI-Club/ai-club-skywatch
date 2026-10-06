"""Tests for precision_recall.

precision_recall is just two divisions, so most of these use counts typed
straight into the test. The last two run the whole chain on the real
fixtures: run_on_fixtures -> confusion_counts -> precision_recall, with the
same fake detectors the other evaluation tests use.
"""

from __future__ import annotations

from pathlib import Path

from scripts.evaluate_spoofing import (
    confusion_counts,
    precision_recall,
    run_on_fixtures,
)

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "air" / "fixtures" / "spoofing"


class AlwaysFiresDetector:
    def detect_observations(self, observations):
        return ["fake detection"] if observations else []


class NeverFiresDetector:
    def detect_observations(self, observations):
        return []


def test_perfect_rule_scores_one_and_one():
    counts = {"tp": 4, "fp": 0, "fn": 0, "tn": 6}
    assert precision_recall(counts) == (1.0, 1.0)


def test_false_alarms_lower_precision_only():
    counts = {"tp": 3, "fp": 1, "fn": 0, "tn": 0}
    assert precision_recall(counts) == (0.75, 1.0)


def test_misses_lower_recall_only():
    counts = {"tp": 1, "fp": 0, "fn": 3, "tn": 0}
    assert precision_recall(counts) == (1.0, 0.25)


def test_flagged_everything_wrong_scores_zero_and_zero():
    counts = {"tp": 0, "fp": 2, "fn": 2, "tn": 0}
    assert precision_recall(counts) == (0.0, 0.0)


def test_nothing_flagged_gives_no_precision():
    counts = {"tp": 0, "fp": 0, "fn": 2, "tn": 5}
    assert precision_recall(counts) == (None, 0.0)


def test_nothing_planted_gives_no_recall():
    counts = {"tp": 0, "fp": 2, "fn": 0, "tn": 5}
    assert precision_recall(counts) == (0.0, None)


def test_all_zero_counts_give_none_and_none():
    counts = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    assert precision_recall(counts) == (None, None)


def test_tn_is_not_needed():
    assert precision_recall({"tp": 1, "fp": 1, "fn": 0}) == (0.5, 1.0)


def test_always_fires_detector_on_real_fixtures():
    counts = confusion_counts(run_on_fixtures(AlwaysFiresDetector(), FIXTURES_DIR))
    # teleport_v1 has one pos_ file and one neg_ file, and both fired:
    # caught everything planted, but half of what it flagged was wrong.
    assert precision_recall(counts["teleport_v1"]) == (0.5, 1.0)


def test_never_fires_detector_on_real_fixtures():
    counts = confusion_counts(run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR))
    # Nothing flagged, so no precision; the one planted teleport was missed.
    assert precision_recall(counts["teleport_v1"]) == (None, 0.0)
