"""Tests for collapsing a run of identical rule hits into one finding.

The risk cuts both ways. Merging too little leaves a queue where one
aircraft misbehaving twelve times reads as twelve aircraft. Merging too much
hides separate findings behind each other, which is worse -- a suppressed
detection is invisible, while a duplicated one is merely noisy.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.episodes import consolidate_episodes, episode_key
from air.detectors.spoofing.records import SpoofingEvent

CFG = SpoofingConfig()
T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def event(
    at_s: float,
    *,
    gate: str = "speed_delta_v1",
    icao24: str = "a1b2c3",
    segment_id: int = 0,
    measured: float | None = 300.0,
    threshold: float | None = 100.0,
    duration_s: float = 2.0,
) -> SpoofingEvent:
    return SpoofingEvent(
        gate=gate,
        detection_type="kinematic_inconsistency",
        reason="SPEED_DISAGREEMENT",
        icao24s=(icao24,),
        observed_from=T0 + timedelta(seconds=at_s),
        observed_to=T0 + timedelta(seconds=at_s + duration_s),
        measured=measured,
        threshold=threshold,
        unit="kt",
        details={"segment_id": segment_id},
    )


def test_a_run_of_hits_becomes_one_finding():
    hits = [event(s) for s in (0, 3, 6, 9, 12)]
    assert len(consolidate_episodes(hits, CFG)) == 1


def test_the_finding_spans_the_whole_episode():
    merged = consolidate_episodes([event(s) for s in (0, 10, 20)], CFG)[0]
    assert merged.observed_from == T0
    assert merged.observed_to == T0 + timedelta(seconds=22)
    assert merged.details["episode_duration_s"] == pytest.approx(22.0)


def test_the_finding_records_how_many_hits_it_stood_for():
    merged = consolidate_episodes([event(s) for s in (0, 3, 6)], CFG)[0]
    assert merged.details["episode_hits"] == 3


def test_the_worst_hit_is_the_one_reported():
    """The extreme moment is what an analyst should be shown."""
    hits = [event(0, measured=150.0), event(3, measured=900.0), event(6, measured=200.0)]
    assert consolidate_episodes(hits, CFG)[0].measured == 900.0


def test_extremity_is_judged_against_each_hit_s_own_threshold():
    """Raw values are not comparable across units; ratios are."""
    small_but_far_over = event(0, measured=90.0, threshold=10.0)   # 9x
    large_but_marginal = event(3, measured=900.0, threshold=800.0)  # 1.1x
    merged = consolidate_episodes([small_but_far_over, large_but_marginal], CFG)[0]
    assert merged.measured == 90.0


def test_different_rules_stay_separate():
    """Two rules firing on one aircraft are two findings, not one."""
    hits = [event(0, gate="speed_delta_v1"), event(1, gate="turn_rate_v1")]
    assert len(consolidate_episodes(hits, CFG)) == 2


def test_different_aircraft_stay_separate():
    hits = [event(0, icao24="a1b2c3"), event(1, icao24="ffffff")]
    assert len(consolidate_episodes(hits, CFG)) == 2


def test_different_segments_stay_separate():
    """The track was already broken there; behaviour either side is not one."""
    hits = [event(0, segment_id=0), event(1, segment_id=1)]
    assert len(consolidate_episodes(hits, CFG)) == 2


def test_a_long_silence_starts_a_new_episode():
    """The same aircraft misbehaving again an hour later is news again."""
    hits = [event(0), event(CFG.episode_gap_s + 120)]
    assert len(consolidate_episodes(hits, CFG)) == 2


def test_hits_inside_the_gap_stay_one_episode():
    hits = [event(0), event(CFG.episode_gap_s - 10)]
    assert len(consolidate_episodes(hits, CFG)) == 1


def test_a_lone_hit_passes_through_unchanged():
    """A single finding must not look different for having been through here."""
    original = event(0)
    merged = consolidate_episodes([original], CFG)[0]
    assert merged.measured == original.measured
    assert merged.threshold == original.threshold
    assert merged.observed_from == original.observed_from
    assert merged.observed_to == original.observed_to
    assert merged.details["episode_hits"] == 1


def test_nothing_in_gives_nothing_out():
    assert consolidate_episodes([], CFG) == []


def test_an_unmeasured_hit_does_not_outrank_a_measured_one():
    """identity_drift carries no quantity; it must not win the comparison."""
    hits = [event(0, measured=None, threshold=None), event(3, measured=500.0)]
    assert consolidate_episodes(hits, CFG)[0].measured == 500.0


def test_an_episode_of_unmeasured_hits_still_reports_one():
    hits = [event(s, measured=None, threshold=None) for s in (0, 3, 6)]
    merged = consolidate_episodes(hits, CFG)
    assert len(merged) == 1
    assert merged[0].details["episode_hits"] == 3


def test_findings_come_back_in_time_order():
    hits = [event(30, icao24="bbbbbb"), event(0, icao24="aaaaaa")]
    out = consolidate_episodes(hits, CFG)
    assert [e.observed_from for e in out] == sorted(e.observed_from for e in out)


def test_hits_arriving_out_of_order_still_group():
    """Events are not guaranteed sorted; the grouping must not depend on it."""
    hits = [event(9), event(0), event(6), event(3)]
    assert len(consolidate_episodes(hits, CFG)) == 1


def test_the_key_is_rule_aircraft_and_segment():
    assert episode_key(event(0)) == ("speed_delta_v1", ("a1b2c3",), 0)


def test_no_hit_is_ever_lost():
    """Every input hit must be accounted for by exactly one finding."""
    hits = [event(s) for s in (0, 3, 6)] + [
        event(s, gate="turn_rate_v1") for s in (0, 3)
    ] + [event(0, icao24="ffffff")]
    out = consolidate_episodes(hits, CFG)
    assert sum(e.details["episode_hits"] for e in out) == len(hits)
