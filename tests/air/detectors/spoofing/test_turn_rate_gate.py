"""Tests for the turn-rate measurability gate.

A gate is only worth having if it closes AND opens. Every case below is paired:
something that must be gated out, and the neighbouring thing that must not be,
so a gate that simply returns ``False`` cannot pass this file.

The boundary gets its own tests because an off-by-one there is invisible in
normal use -- almost every record sits well clear of the floor, so a wrong
comparison still looks right until the one record that lands exactly on it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.records import SpoofingFeatureRecord
from air.detectors.spoofing.turn_rate_gate import (
    DEFAULT_TURN_RATE_MIN_SPEED_KT,
    is_turn_rate_measurable,
    turn_rate_min_speed_kt,
)

CFG = SpoofingConfig()
T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def record(**overrides) -> SpoofingFeatureRecord:
    """A pair record that is measurable unless a test says otherwise."""
    values = dict(
        icao24="a1b2c3",
        segment_id=0,
        prev_observed_at=T0,
        curr_observed_at=T0 + timedelta(seconds=8),
        dt_s=8.0,
        dist_m=1000.0,
        reported_speed_kt=450.0,
        turn_rate_dps=2.0,
    )
    values.update(overrides)
    return SpoofingFeatureRecord(**values)


@dataclass(frozen=True)
class FakeCfg:
    """Stands in for a SpoofingConfig that already carries the new setting.

    SpoofingConfig does not define ``turn_rate_min_speed_kt`` yet, so the real
    config can only exercise the getattr fallback. This covers the other half:
    that once the field exists, the gate reads it.
    """

    turn_rate_min_speed_kt: float | None = 150.0


# --- the two documented rejections -------------------------------------------
def test_missing_reported_speed_is_not_measurable():
    """No speed reported means no basis for trusting the heading.

    Abstain rather than assume the aircraft was fast enough.
    """
    assert is_turn_rate_measurable(record(reported_speed_kt=None), CFG) is False


def test_speed_below_the_floor_is_not_measurable():
    """55 kt is the median speed on the alerts this gate exists to remove."""
    assert is_turn_rate_measurable(record(reported_speed_kt=55.0), CFG) is False


def test_fast_aircraft_is_measurable():
    assert is_turn_rate_measurable(record(reported_speed_kt=450.0), CFG) is True


# --- the boundary -------------------------------------------------------------
def test_exactly_at_the_floor_is_measurable():
    """The floor is the lowest speed still trusted, not the first rejected."""
    assert is_turn_rate_measurable(
        record(reported_speed_kt=DEFAULT_TURN_RATE_MIN_SPEED_KT), CFG
    ) is True


def test_just_under_the_floor_is_not_measurable():
    assert is_turn_rate_measurable(
        record(reported_speed_kt=DEFAULT_TURN_RATE_MIN_SPEED_KT - 0.1), CFG
    ) is False


def test_just_over_the_floor_is_measurable():
    assert is_turn_rate_measurable(
        record(reported_speed_kt=DEFAULT_TURN_RATE_MIN_SPEED_KT + 0.1), CFG
    ) is True


# --- the alert distribution this gate was built from ---------------------------
@pytest.mark.parametrize("speed_kt", [0.0, 5.0, 12.0, 30.0, 55.0, 100.0, 149.9])
def test_taxi_and_slow_traffic_is_gated_out(speed_kt):
    """93% of turn-rate alerts came from speeds in this range."""
    assert is_turn_rate_measurable(record(reported_speed_kt=speed_kt), CFG) is False


@pytest.mark.parametrize("speed_kt", [150.0, 180.0, 250.0, 450.0, 780.0])
def test_airborne_traffic_is_let_through(speed_kt):
    """The gate must not cost the rule its reach where it works."""
    assert is_turn_rate_measurable(record(reported_speed_kt=speed_kt), CFG) is True


# --- a stationary transponder is the pathological case -------------------------
def test_parked_aircraft_reporting_a_wild_turn_is_gated_out():
    """A transponder at 0 kt can report any heading change at all.

    This is the case the gate most needs to catch: the turn rate is far past
    the threshold, and completely meaningless.
    """
    assert is_turn_rate_measurable(
        record(reported_speed_kt=0.0, turn_rate_dps=179.0), CFG
    ) is False


def test_gate_ignores_the_turn_rate_itself():
    """Measurability is a property of the speed, not of the answer.

    If the gate consulted turn_rate_dps it would be doing the rule's job, and
    an abstention would stop being distinguishable from a pass.
    """
    fast = record(reported_speed_kt=450.0, turn_rate_dps=0.0)
    wild = record(reported_speed_kt=450.0, turn_rate_dps=90.0)
    assert is_turn_rate_measurable(fast, CFG) is is_turn_rate_measurable(wild, CFG)


def test_gate_ignores_missing_turn_rate():
    """Whether the record carries a turn rate is flag_turn_rate's concern."""
    assert is_turn_rate_measurable(
        record(reported_speed_kt=450.0, turn_rate_dps=None), CFG
    ) is True


# --- bad numbers ----------------------------------------------------------------
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_speed_is_not_measurable(bad):
    """A broken decode is not a speed, whichever direction it is broken in.

    NaN is the one that matters: it compares ``False`` against everything, so
    without an explicit finiteness check it would read as measurable and slip
    past the floor. Both infinities are rejected with it rather than special-
    cased -- ``+inf`` would clear any floor and let the rule judge a turn rate
    derived from a speed the aircraft cannot have reported, which is the
    opposite of what a measurability gate is for.
    """
    assert is_turn_rate_measurable(record(reported_speed_kt=bad), CFG) is False


def test_integer_speed_is_accepted():
    """Fixtures and hand-built records carry ints; floats must not be assumed."""
    assert is_turn_rate_measurable(record(reported_speed_kt=450), CFG) is True


# --- config resolution ------------------------------------------------------------
def test_falls_back_to_the_default_before_the_setting_exists():
    """SpoofingConfig has no turn_rate_min_speed_kt yet; the gate still works."""
    assert not hasattr(CFG, "turn_rate_min_speed_kt")
    assert turn_rate_min_speed_kt(CFG) == DEFAULT_TURN_RATE_MIN_SPEED_KT


def test_reads_the_setting_once_the_config_carries_it():
    cfg = FakeCfg(turn_rate_min_speed_kt=200.0)
    assert turn_rate_min_speed_kt(cfg) == 200.0
    assert is_turn_rate_measurable(record(reported_speed_kt=180.0), cfg) is False
    assert is_turn_rate_measurable(record(reported_speed_kt=220.0), cfg) is True


def test_a_configured_none_disables_the_gate():
    """A None floor means 'no floor', not a crash comparing against None."""
    cfg = FakeCfg(turn_rate_min_speed_kt=None)
    assert turn_rate_min_speed_kt(cfg) == 0.0
    assert is_turn_rate_measurable(record(reported_speed_kt=5.0), cfg) is True
    # A missing speed is still unmeasurable -- that rejection is independent
    # of the floor.
    assert is_turn_rate_measurable(record(reported_speed_kt=None), cfg) is False


def test_a_zero_floor_still_rejects_missing_speed():
    cfg = FakeCfg(turn_rate_min_speed_kt=0.0)
    assert is_turn_rate_measurable(record(reported_speed_kt=0.0), cfg) is True
    assert is_turn_rate_measurable(record(reported_speed_kt=None), cfg) is False


# --- the gate must not cost the rule its positive -------------------------------
def test_the_impossible_turn_fixture_survives_the_gate(observations_from):
    """pos_impossible_turn.json must still reach flag_turn_rate.

    This is the recall guard. A gate that silences the one fixture the rule
    exists to catch has traded 156 false alarms for the detection itself, and
    every other test in this file would still pass. Raise the floor past
    450 kt and this is what fails.
    """
    from air.detectors.spoofing.features import (
        build_pair_features,
        group_by_aircraft,
        split_segments,
    )
    from air.detectors.spoofing.physics import flag_turn_rate

    observations = observations_from("spoofing/pos_impossible_turn.json")

    firing = []
    for track in group_by_aircraft(observations).values():
        for segment_id, segment in enumerate(split_segments(track, CFG.max_gap_s)):
            for previous, current in zip(segment, segment[1:]):
                pair = build_pair_features(previous, current, segment_id)
                if pair is None:
                    continue
                if flag_turn_rate(pair, CFG) is not None:
                    firing.append(pair)

    assert firing, "fixture no longer trips flag_turn_rate at all"
    assert all(is_turn_rate_measurable(pair, CFG) for pair in firing), (
        "the gate suppresses the impossible-turn fixture; the floor is too high"
    )


def test_returns_a_real_bool_not_something_truthy():
    """The caller is a guard clause; `is False` must behave as written."""
    assert isinstance(is_turn_rate_measurable(record(), CFG), bool)
    assert isinstance(
        is_turn_rate_measurable(record(reported_speed_kt=None), CFG), bool
    )
