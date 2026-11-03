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
    # PROX-5: dedup is on for tumbling windows too. An encounter spanning a
    # window edge is a genuine converging pair in both halves, so the runner has
    # to collapse them -- a detector call cannot see the previous window.
    return list(run_detectors(iter_windows(obs, window_s, step), [ProximityDetector()], dedup=True))


def test_fixture_really_straddles_a_window_edge():
    windows = list(iter_windows(load_observations(FIXTURE), 60))
    assert len(windows) == 2
    for window in windows:
        assert {o.icao24 for o in window} == {"aaa001", "bbb002"}


def test_one_shot_counts_the_encounter_once():
    assert len(ProximityDetector().detect_observations(load_observations(FIXTURE))) == 1


def test_whole_stream_as_one_window_counts_it_once():
    assert len(_windowed(3600)) == 1


def test_each_window_alone_flags_the_pair():
    # Not a bug in the detector: each half of the encounter, seen on its own,
    # really is a converging pair inside max_tcpa_s.
    for window in iter_windows(load_observations(FIXTURE), 60):
        assert len(ProximityDetector().detect_observations(window)) == 1


def test_dedup_key_matches_across_windows():
    # PROX-5 fix: temporal_bounds is anchored to the predicted closest approach,
    # which every window computes identically (to a few microseconds, rounded to
    # the second), rather than to the tick the pair happened to be evaluated at.
    # So the dedup key is the same from either window and the runner collapses
    # the two halves into one encounter.
    first, second = (ProximityDetector().detect_observations(w)[0] for w in iter_windows(load_observations(FIXTURE), 60))
    assert detection_dedup_key(first) == detection_dedup_key(second)
    assert first.temporal_bounds.start_time == second.temporal_bounds.start_time


@pytest.mark.parametrize("window_s", [60, 30])
def test_tumbling_windows_count_the_encounter_once(window_s):
    assert len(_windowed(window_s)) == 1


def test_sliding_windows_with_dedup_count_the_encounter_once():
    assert len(_windowed(60, 20)) == 1
