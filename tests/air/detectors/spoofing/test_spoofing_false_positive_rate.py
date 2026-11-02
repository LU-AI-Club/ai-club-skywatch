"""Tests for alerts_per_hour and attribute_false_positives."""

from __future__ import annotations

import pytest

from scripts.evaluate_spoofing import alerts_per_hour, attribute_false_positives


def result(name: str, expected_positive: bool, fired: bool) -> dict:
    return {
        "fixture_name": name,
        "expected_positive": expected_positive,
        "expected_gate": name.split("_", 1)[-1].removesuffix(".json"),
        "detections": [object()] if fired else [],
        "fired": fired,
    }


# --- alerts_per_hour ---------------------------------------------------------
def test_alerts_divided_by_hours():
    assert alerts_per_hour(["a", "b", "c", "d"], 2.0) == 2.0


def test_a_quiet_hour_is_zero():
    assert alerts_per_hour([], 1.0) == 0.0


def test_a_fractional_window():
    """One alert in fifteen minutes is four an hour."""
    assert alerts_per_hour(["a"], 0.25) == 4.0


@pytest.mark.parametrize("hours", [0.0, -1.0])
def test_an_empty_window_returns_zero_rather_than_raising(hours):
    assert alerts_per_hour(["a"], hours) == 0.0


def test_the_number_that_decides_usability():
    """400 an hour means nobody reads any of them."""
    assert alerts_per_hour(list(range(400)), 1.0) == 400.0


# --- attribute_false_positives -----------------------------------------------
def test_only_wrong_alarms_are_counted():
    results = [
        result("neg_tailwind_cruise.json", False, True),    # false positive
        result("pos_teleport.json", True, True),            # correct catch
        result("neg_standard_turn.json", False, False),     # correct quiet
        result("pos_impersonation.json", True, False),      # a miss, not an alarm
    ]
    assert attribute_false_positives(results) == [("tailwind_cruise", 1)]


def test_causes_are_sorted_worst_first():
    results = [
        result("neg_tailwind_cruise.json", False, True),
        result("neg_tailwind_cruise.json", False, True),
        result("neg_standard_turn.json", False, True),
    ]
    assert attribute_false_positives(results) == [
        ("tailwind_cruise", 2),
        ("standard_turn", 1),
    ]


def test_a_clean_run_attributes_nothing():
    assert attribute_false_positives([result("pos_teleport.json", True, True)]) == []


def test_no_results_at_all():
    assert attribute_false_positives([]) == []
