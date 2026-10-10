"""Tests for sweep_threshold.

No real spoofing detector exists yet, so this sweeps a hand-built fake one:
it fires on a fixture if any row reports a ground speed over `limit_kt`.
That is not a real spoofing rule, but it does change its answer as the limit
moves, which is the thing sweep_threshold has to show.

The fixtures' highest reported ground speeds are: 780 kt in
neg_tailwind_cruise.json, 450 kt in all 8 pos_ files and 4 other negatives,
and 320 kt or less in the remaining 4 negatives.
"""

from __future__ import annotations

from pathlib import Path

from scripts.evaluate_spoofing import sweep_threshold

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "air" / "fixtures" / "spoofing"


class FakeSpeedLimitDetector:
    def __init__(self, limit_kt: float) -> None:
        self.limit_kt = limit_kt

    def detect_observations(self, observations):
        for obs in observations:
            if obs.ground_speed_kt is not None and obs.ground_speed_kt > self.limit_kt:
                return ["fake detection"]
        return []


def make_fake_detector(settings: dict) -> FakeSpeedLimitDetector:
    return FakeSpeedLimitDetector(settings["limit_kt"])


def test_one_row_per_value_in_the_order_given():
    table = sweep_threshold("limit_kt", [1000, 400, 500], FIXTURES_DIR, make_fake_detector)
    assert [row["value"] for row in table] == [1000, 400, 500]
    assert all(row["setting"] == "limit_kt" for row in table)


def test_limit_above_every_speed_does_not_fire():
    table = sweep_threshold("limit_kt", [1000], FIXTURES_DIR, make_fake_detector)
    assert table == [
        {
            "setting": "limit_kt",
            "value": 1000,
            "tp": 0,
            "fp": 0,
            "fn": 8,
            "tn": 9,
            "precision": None,
            "recall": 0.0,
        }
    ]


def test_limit_just_under_the_tailwind_gives_one_false_alarm():
    table = sweep_threshold("limit_kt", [500], FIXTURES_DIR, make_fake_detector)
    row = table[0]
    assert (row["tp"], row["fp"], row["fn"], row["tn"]) == (0, 1, 8, 8)
    assert (row["precision"], row["recall"]) == (0.0, 0.0)


def test_low_limit_fires_on_every_positive_and_some_negatives():
    table = sweep_threshold("limit_kt", [400], FIXTURES_DIR, make_fake_detector)
    row = table[0]
    assert (row["tp"], row["fp"], row["fn"], row["tn"]) == (8, 5, 0, 4)
    assert row["precision"] == 8 / 13
    assert row["recall"] == 1.0


def test_lowering_the_limit_never_lowers_recall():
    table = sweep_threshold("limit_kt", [1000, 500, 400, 0], FIXTURES_DIR, make_fake_detector)
    recalls = [row["recall"] for row in table]
    assert recalls == sorted(recalls)
    assert recalls[0] == 0.0
    assert recalls[-1] == 1.0


def test_every_row_adds_up_to_the_number_of_fixtures():
    table = sweep_threshold("limit_kt", [1000, 500, 400, 0], FIXTURES_DIR, make_fake_detector)
    json_files = list(FIXTURES_DIR.glob("*.json"))
    for row in table:
        assert row["tp"] + row["fp"] + row["fn"] + row["tn"] == len(json_files)


def test_make_detector_is_given_the_setting_and_value():
    seen = []

    def remember(settings: dict) -> FakeSpeedLimitDetector:
        seen.append(settings)
        return FakeSpeedLimitDetector(1000)

    sweep_threshold("teleport_kt", [800, 900], FIXTURES_DIR, remember)
    assert seen == [{"teleport_kt": 800}, {"teleport_kt": 900}]


def test_no_values_gives_an_empty_table():
    assert sweep_threshold("limit_kt", [], FIXTURES_DIR, make_fake_detector) == []
