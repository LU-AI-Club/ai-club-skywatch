from __future__ import annotations

from datetime import datetime, timezone

import pytest

from air.detectors.spoofing.quality import fix_quality_factor
from air.detectors.spoofing.records import SpoofingFeatureRecord


def make_record(**quality_fields: int | None) -> SpoofingFeatureRecord:
    return SpoofingFeatureRecord(
        icao24="abc123",
        segment_id=0,
        prev_observed_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        curr_observed_at=datetime(2025, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        dt_s=1.0,
        dist_m=0.0,
        **quality_fields,
    )


def test_returns_neutral_factor_when_all_quality_values_are_missing():
    assert fix_quality_factor(make_record()) == 1.0


def test_normalizes_highest_quality_codes_to_one():
    record = make_record(nic=11, nacp=11)
    assert fix_quality_factor(record) == 1.0


def test_normalizes_lowest_quality_codes_to_zero():
    record = make_record(nic=0, nacp=0)
    assert fix_quality_factor(record) == 0.0


@pytest.mark.parametrize(
    ("quality_fields", "expected"),
    [
        ({"nic": 5}, 5 / 11),
        ({"nacp": 5}, 5 / 11),
        ({"nic": 11, "nacp": None}, 1.0),
        ({"nic": None, "nacp": 5}, 5 / 11),
    ],
)
def test_uses_each_available_quality_value(quality_fields, expected):
    factor = fix_quality_factor(make_record(**quality_fields))
    assert factor == pytest.approx(expected)
    assert 0.0 <= factor <= 1.0


def test_averages_nic_and_nacp_when_both_are_available():
    record = make_record(nic=11, nacp=5)
    assert fix_quality_factor(record) == pytest.approx(8 / 11)


@pytest.mark.parametrize(("code", "expected"), [(-1, 0.0), (12, 1.0)])
def test_clamps_values_outside_the_defined_code_range(code: int, expected: float):
    factor = fix_quality_factor(make_record(nic=code))
    assert factor == expected
    assert 0.0 <= factor <= 1.0
