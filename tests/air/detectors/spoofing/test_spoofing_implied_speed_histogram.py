"""Tests for implied_speed_histogram.

The chart needs matplotlib, which is only in the `eda` extras, so this whole
file is skipped on a machine that does not have it (`pip install ".[eda]"`).

Nothing builds SpoofingFeatureRecord objects from fixtures yet (that is the
features lane), so the records here are made up in the test. Only
`implied_speed_kt` is read, so a SimpleNamespace with that one field is
enough. The tests read the bar heights back off the chart rather than
looking at a picture.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("matplotlib")

from scripts.evaluate_spoofing import implied_speed_histogram  # noqa: E402


def records_with_speeds(speeds: list) -> list[SimpleNamespace]:
    return [SimpleNamespace(implied_speed_kt=speed) for speed in speeds]


def bar_heights(fig) -> list[float]:
    return [bar.get_height() for bar in fig.axes[0].patches]


def test_speeds_are_counted_into_the_right_bars():
    records = records_with_speeds([10, 20, 449, 451, 780])
    fig = implied_speed_histogram(records, bin_width_kt=50, max_kt=2000)
    heights = bar_heights(fig)
    assert heights[0] == 2    # 10 and 20 are in 0-50
    assert heights[8] == 1    # 449 is in 400-450
    assert heights[9] == 1    # 451 is in 450-500
    assert heights[15] == 1   # 780 is in 750-800
    assert sum(heights) == 5


def test_impossible_speeds_go_in_the_last_bar():
    records = records_with_speeds([450, 21285, 34000])
    fig = implied_speed_histogram(records, bin_width_kt=50, max_kt=2000)
    heights = bar_heights(fig)
    assert len(heights) == 41  # 40 bars from 0 to 2000, plus one for "2000+"
    assert heights[-1] == 2
    assert heights[9] == 1


def test_speed_exactly_at_max_goes_in_the_last_bar():
    fig = implied_speed_histogram(records_with_speeds([2000]), bin_width_kt=50, max_kt=2000)
    assert bar_heights(fig)[-1] == 1


def test_records_without_a_speed_are_left_out():
    records = records_with_speeds([450, None, None])
    fig = implied_speed_histogram(records)
    assert sum(bar_heights(fig)) == 1


def test_no_speeds_at_all_gives_no_chart():
    assert implied_speed_histogram([]) is None
    assert implied_speed_histogram(records_with_speeds([None, None])) is None


def test_limit_line_is_drawn_at_teleport_kt():
    fig = implied_speed_histogram(records_with_speeds([450]), teleport_kt=1200)
    line = fig.axes[0].lines[0]
    assert list(line.get_xdata()) == [1200, 1200]


def test_limit_line_defaults_to_1000_kt():
    fig = implied_speed_histogram(records_with_speeds([450]))
    line = fig.axes[0].lines[0]
    assert list(line.get_xdata()) == [1000, 1000]


def test_chart_can_be_saved_to_a_file(tmp_path):
    fig = implied_speed_histogram(records_with_speeds([450, 780, 34000]))
    out = tmp_path / "chart.png"
    fig.savefig(out)
    assert out.stat().st_size > 0
