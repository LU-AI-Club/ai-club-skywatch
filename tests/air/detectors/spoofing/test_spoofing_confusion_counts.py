"""Tests for confusion_counts.

confusion_counts only counts and groups a list, so most of these use a short
made-up list typed straight into the test. The last two run it on the real
fixtures through run_on_fixtures, with the same fake detectors that
test_spoofing_run_on_fixtures.py uses.
"""

from __future__ import annotations

from pathlib import Path

from scripts.evaluate_spoofing import confusion_counts, run_on_fixtures

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "air" / "fixtures" / "spoofing"


class AlwaysFiresDetector:
    def detect_observations(self, observations):
        return ["fake detection"] if observations else []


class NeverFiresDetector:
    def detect_observations(self, observations):
        return []


def result(gate: str, expected_positive: bool, fired: bool) -> dict:
    return {
        "fixture_name": "made_up.json",
        "expected_positive": expected_positive,
        "expected_gate": gate,
        "detections": ["fake detection"] if fired else [],
        "fired": fired,
    }


def test_catch_is_counted_as_tp():
    counts = confusion_counts([result("teleport_v1", True, True)])
    assert counts == {"teleport_v1": {"tp": 1, "fp": 0, "fn": 0, "tn": 0}}


def test_miss_is_counted_as_fn():
    counts = confusion_counts([result("teleport_v1", True, False)])
    assert counts == {"teleport_v1": {"tp": 0, "fp": 0, "fn": 1, "tn": 0}}


def test_false_alarm_is_counted_as_fp():
    counts = confusion_counts([result("teleport_v1", False, True)])
    assert counts == {"teleport_v1": {"tp": 0, "fp": 1, "fn": 0, "tn": 0}}


def test_correct_quiet_is_counted_as_tn():
    counts = confusion_counts([result("teleport_v1", False, False)])
    assert counts == {"teleport_v1": {"tp": 0, "fp": 0, "fn": 0, "tn": 1}}


def test_counts_are_kept_separate_per_rule():
    counts = confusion_counts(
        [
            result("teleport_v1", True, True),
            result("teleport_v1", False, False),
            result("turn_rate_v1", True, False),
            result("turn_rate_v1", False, True),
            result("turn_rate_v1", False, True),
        ]
    )
    assert counts == {
        "teleport_v1": {"tp": 1, "fp": 0, "fn": 0, "tn": 1},
        "turn_rate_v1": {"tp": 0, "fp": 2, "fn": 1, "tn": 0},
    }


def test_empty_results_give_empty_counts():
    assert confusion_counts([]) == {}


def test_never_fires_detector_only_misses_and_correct_quiets():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    counts = confusion_counts(results)
    assert counts["teleport_v1"] == {"tp": 0, "fp": 0, "fn": 1, "tn": 1}
    assert all(c["tp"] == 0 and c["fp"] == 0 for c in counts.values())


def test_always_fires_detector_only_catches_and_false_alarms():
    results = run_on_fixtures(AlwaysFiresDetector(), FIXTURES_DIR)
    counts = confusion_counts(results)
    assert counts["teleport_v1"] == {"tp": 1, "fp": 1, "fn": 0, "tn": 0}
    assert all(c["fn"] == 0 and c["tn"] == 0 for c in counts.values())
    total = sum(sum(c.values()) for c in counts.values())
    assert total == len(results)
