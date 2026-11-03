"""PROX-5: one encounter, counted several times. OWNER: Erik.

The runner (air/windowing.py, scripts/replay_csv.py) slices the stream into
epoch-anchored windows and calls detect_observations() once per window. The
detector keeps one detection per pair *within* a call, but nothing links one
window to the next, so an encounter that crosses a window edge is emitted once
per window.

The xfail tests below pin the behaviour we want. They are strict: when the fix
lands they XPASS, strict turns that into a failure, and whoever fixes it must
delete the xfail marker in the same PR.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_windowing.py -q -rxX
"""

from __future__ import annotations

import pytest

from air.detectors.proximity import ProximityDetector
from air.windowing import detection_dedup_key, iter_windows, run_detectors
from tests.conftest import load_observations

FIXTURE = "proximity_spans_window.json"


def _windowed(window_s, step_s=None):
    obs = load_observations(FIXTURE)
    step = window_s if step_s is None else step_s
    # Mirrors scripts/replay_csv.py: dedup only when windows overlap, because
    # that is the case where the same moment is evaluated twice.
    return list(run_detectors(iter_windows(obs, window_s, step), [ProximityDetector()], dedup=step < window_s))


def _n(window_s, step_s=None):
    return len(_windowed(window_s, step_s))


def test_fixture_really_straddles_a_window_edge():
    windows = list(iter_windows(load_observations(FIXTURE), 60))
    assert len(windows) == 2
    for window in windows:
        assert {o.icao24 for o in window} == {"aaa001", "bbb002"}


def test_one_shot_alerts_once_per_cooldown_period():
    # The fixture's 40 s of reports straddle a 60 s period boundary, so two.
    assert len(ProximityDetector().detect_observations(load_observations(FIXTURE))) == 2


def test_the_answer_does_not_depend_on_how_time_is_sliced():
    """The point of epoch-anchored cooldown periods: one 3,600 s window, 60 s
    tumbling, 30 s tumbling and 60/20 sliding all see the same encounter and
    all report it the same number of times."""
    assert _n(3600) == _n(60) == _n(30) == _n(60, 20) == 2


def test_each_window_alone_flags_the_pair():
    # Not a bug in the detector: each half of the encounter, seen on its own,
    # really is a converging pair inside max_tcpa_s.
    for window in iter_windows(load_observations(FIXTURE), 60):
        assert len(ProximityDetector().detect_observations(window)) == 1


def test_dedup_key_is_stable_for_the_same_period_across_windows():
    """Sliding windows overlap, so more than one of them covers a given
    cooldown period. Each produces the SAME key for it, because
    temporal_bounds.start_time is the period -- anchored to the epoch rather
    than to whichever tick we happened to evaluate at. That is what lets the
    runner's dedup collapse the repeats instead of writing duplicate rows.
    """
    obs = load_observations(FIXTURE)
    keys = [
        [detection_dedup_key(d) for d in ProximityDetector().detect_observations(w)]
        for w in iter_windows(obs, 60, 20)
    ]
    flat = [k for window in keys for k in window]
    assert len(flat) > len(set(flat)), "sliding windows should re-report a period"
    assert len(set(flat)) == _n(60, 20), "dedup should leave exactly the distinct periods"


def test_consecutive_periods_get_different_keys():
    # ...and the two periods of one encounter stay distinct, so the detection
    # table keeps both rows for the front end to group.
    alerts = ProximityDetector().detect_observations(load_observations(FIXTURE))
    assert len({detection_dedup_key(d) for d in alerts}) == len(alerts)


@pytest.mark.parametrize("window_s", [60, 30])
def test_tumbling_windows_alert_once_per_cooldown_period(window_s):
    """Decided with the Tech Lead (2026-11-03): an ongoing encounter SHOULD
    produce several alerts, and the front end groups them per pair. Consecutive
    windows evaluate different moments, so each legitimately alerts; the
    detector's alert_cooldown_s is what keeps them from being too frequent.

    This fixture's reports run 00:30:40 to 00:31:20, so they fall in two
    windows at both 60 s and 30 s. Two windows, two alerts.
    """
    assert _n(window_s) == 2





def test_sliding_windows_do_not_multiply_the_alerts():
    """Overlapping windows re-evaluate moments they have already covered, which
    is a genuine duplicate. Dedup collapses them -- and it only works because
    temporal_bounds is anchored to the predicted closest approach rather than
    to whichever tick we happened to evaluate at.

    A 20 s step over 60 s windows covers this encounter three times as often as
    tumbling does, and still produces no more alerts.
    """
    assert _n(60, 20) == _n(60)
