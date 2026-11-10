"""Tests for fix_quality_factor, which reads the aircraft's own NIC/NACp.

Every rule gets a case that moves the number and a case that does not. A
factor that returns 1.0 for everything would pass a one-sided test and
change nothing downstream.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.quality import (
    FLOOR,
    NACP_BEST,
    NIC_BEST,
    fix_quality_factor,
)
from air.detectors.spoofing.records import SpoofingFeatureRecord

T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def record(**overrides) -> SpoofingFeatureRecord:
    values = dict(
        icao24="a1b2c3",
        segment_id=0,
        prev_observed_at=T0,
        curr_observed_at=T0 + timedelta(seconds=8),
        dt_s=8.0,
        dist_m=1000.0,
    )
    values.update(overrides)
    return SpoofingFeatureRecord(**values)


def test_a_perfect_fix_on_both_rows_scores_one():
    best = record(
        prev_nic=NIC_BEST, nic=NIC_BEST, prev_nacp=NACP_BEST, nacp=NACP_BEST
    )
    assert fix_quality_factor(best) == 1.0


def test_silence_is_not_held_against_the_aircraft():
    """A feed without these fields must not down-rank every aircraft on it."""
    assert fix_quality_factor(record()) == 1.0


def test_a_poor_fix_lowers_the_factor():
    poor = record(nic=2, nacp=2, prev_nic=2, prev_nacp=2)
    assert fix_quality_factor(poor) < 1.0


def test_the_worst_value_present_decides():
    """The measurement spans both rows, so the weaker row bounds the pair."""
    mixed = record(
        prev_nic=NIC_BEST, nic=NIC_BEST, prev_nacp=NACP_BEST, nacp=4
    )
    assert fix_quality_factor(mixed) == pytest.approx(4 / NACP_BEST, abs=0.001)


def test_one_bad_row_after_a_good_one_is_a_bad_pair():
    degrading = record(prev_nic=NIC_BEST, nic=1)
    assert fix_quality_factor(degrading) == pytest.approx(
        max(FLOOR, 1 / NIC_BEST), abs=0.001
    )


def test_a_single_reported_value_is_enough():
    """Partial reporting is common; use what we were given."""
    assert fix_quality_factor(record(nacp=NACP_BEST)) == 1.0
    assert fix_quality_factor(record(nacp=4)) == pytest.approx(
        4 / NACP_BEST, abs=0.001
    )


def test_the_factor_never_falls_below_the_floor():
    """A gross teleport is still a teleport when the GPS is admittedly bad."""
    worst = record(prev_nic=0, nic=0, prev_nacp=0, nacp=0)
    assert fix_quality_factor(worst) == FLOOR


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"nic": 0},
        {"nacp": 0},
        {"nic": NIC_BEST, "nacp": NACP_BEST},
        {"prev_nic": 5, "nic": 7, "prev_nacp": 9, "nacp": 8},
        {"nic": 99, "nacp": -4},  # malformed, out of range
    ],
)
def test_the_factor_always_lands_in_range(fields):
    assert FLOOR <= fix_quality_factor(record(**fields)) <= 1.0


def test_out_of_range_values_are_clamped_not_rejected():
    """A malformed field should weaken the alert, not crash the detector."""
    assert fix_quality_factor(record(nic=99)) == 1.0
    assert fix_quality_factor(record(nic=-4)) == FLOOR


def test_a_better_fix_never_scores_lower_than_a_worse_one():
    factors = [
        fix_quality_factor(record(nic=value, nacp=value))
        for value in range(0, NIC_BEST + 1)
    ]
    assert factors == sorted(factors)
