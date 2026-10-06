from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import pytest

from air.detectors.spoofing.identity import flag_pingpong

# Two points ~175 km apart (east-west), and one offset north of A.
A = (38.0, -79.0)
B = (38.0, -77.0)
A_NORTH = (38.3, -79.0)   # ~33 km north of A
D = (39.0, -77.0)         # north of B
E = (39.0, -75.0)         # east of D
F = (40.0, -75.0)         # north of E

STEP = 10  # seconds between records


def rec(t, pos):
    return {"timestamp": t, "lat": pos[0], "lon": pos[1]}


def track(positions, step=STEP):
    return [rec(i * step, p) for i, p in enumerate(positions)]


@pytest.fixture
def cfg():
    return NS(max_speed_mps=450.0, pingpong_min_hops=3)


# --- should fire -----------------------------------------------------------

def test_fires_on_exactly_three_hops(cfg):
    # A,B,A,B = 3 impossible hops, each reversing
    result = flag_pingpong(track([A, B, A, B]), cfg)
    assert result is not None
    assert "pingpong" in result
    assert "3 consecutive" in result


def test_fires_on_longer_pingpong(cfg):
    result = flag_pingpong(track([A, B, A, B, A, B, A]), cfg)
    assert result is not None
    assert "6 consecutive" in result or "3 consecutive" in result


def test_fires_when_pingpong_starts_after_normal_flight(cfg):
    normal = [(38.0, -79.0 + i * 0.01) for i in range(5)]
    start = normal[-1]
    positions = normal + [B, start, B, start]
    assert flag_pingpong(track(positions), cfg) is not None


def test_fires_after_normal_flight_follows(cfg):
    positions = [A, B, A, B, B, B, B]
    assert flag_pingpong(track(positions), cfg) is not None


def test_unsorted_input_is_sorted_by_timestamp(cfg):
    records = track([A, B, A, B, A])
    records.reverse()
    assert flag_pingpong(records, cfg) is not None


def test_datetime_timestamps(cfg):
    t0 = datetime(2026, 10, 6, 12, 0, 0, tzinfo=timezone.utc)
    records = [
        {"timestamp": t0 + timedelta(seconds=i * STEP), "lat": p[0], "lon": p[1]}
        for i, p in enumerate([A, B, A, B])
    ]
    assert flag_pingpong(records, cfg) is not None


def test_object_records(cfg):
    records = [
        NS(timestamp=i * STEP, lat=p[0], lon=p[1])
        for i, p in enumerate([A, B, A, B])
    ]
    assert flag_pingpong(records, cfg) is not None


def test_simultaneous_positions_count_as_impossible(cfg):
    # Same timestamp, two different places, flipping back and forth
    records = [rec(0, p) for p in [A, B, A, B]]
    result = flag_pingpong(records, cfg)
    assert result is not None
    assert "simultaneous" in result


def test_reason_mentions_limit_and_distance(cfg):
    result = flag_pingpong(track([A, B, A, B]), cfg)
    assert "450 m/s" in result
    assert "km apart" in result


# --- should NOT fire -------------------------------------------------------

def test_single_bad_position_does_not_fire(cfg):
    # One faked point: out and back = only 2 impossible hops
    assert flag_pingpong(track([A, A, B, A, A]), cfg) is None


def test_one_way_teleport_does_not_fire(cfg):
    assert flag_pingpong(track([A, A, B, B, B]), cfg) is None


def test_two_flips_is_not_enough(cfg):
    # A,B,A,B has 3 hops; A,B,A has only 2
    assert flag_pingpong(track([A, B, A]), cfg) is None


def test_normal_flight_does_not_fire(cfg):
    positions = [(38.0, -79.0 + i * 0.01) for i in range(10)]
    assert flag_pingpong(track(positions), cfg) is None


def test_impossible_hops_that_keep_going_one_direction_do_not_fire(cfg):
    # Staircase of impossible hops, never reversing (90 degree turns)
    assert flag_pingpong(track([A, B, D, E, F]), cfg) is None


def test_plausible_hop_breaks_the_run(cfg):
    # imp, imp, plausible (A->A), imp, imp: never 3 in a row
    assert flag_pingpong(track([A, B, A, A, B, A]), cfg) is None


def test_same_position_same_timestamp_is_not_impossible(cfg):
    records = [rec(0, A) for _ in range(5)]
    assert flag_pingpong(records, cfg) is None


@pytest.mark.parametrize("n", [0, 1, 2, 3])
def test_too_few_records(cfg, n):
    assert flag_pingpong(track([A, B, A, B][:n]), cfg) is None


# --- config behavior -------------------------------------------------------

def test_min_hops_raised(cfg):
    cfg.pingpong_min_hops = 4
    assert flag_pingpong(track([A, B, A, B]), cfg) is None        # 3 hops
    assert flag_pingpong(track([A, B, A, B, A]), cfg) is not None  # 4 hops


def test_min_hops_lowered_makes_single_spoof_fire(cfg):
    cfg.pingpong_min_hops = 2
    assert flag_pingpong(track([A, A, B, A, A]), cfg) is not None


def test_max_speed_raised_makes_hops_possible(cfg):
    cfg.max_speed_mps = 1_000_000.0
    assert flag_pingpong(track([A, B, A, B, A]), cfg) is None


def test_slower_records_become_possible(cfg):
    # 175 km in 1 hour is ~49 m/s, which is plausible
    assert flag_pingpong(track([A, B, A, B, A], step=3600), cfg) is None


def test_reversal_tolerance(cfg):
    # Return leg is ~10 degrees off a perfect reversal
    records = track([A, B, A_NORTH, B])
    cfg.pingpong_reversal_tolerance_deg = 45.0
    assert flag_pingpong(records, cfg) is not None
    cfg.pingpong_reversal_tolerance_deg = 5.0
    assert flag_pingpong(records, cfg) is None


def test_defaults_used_when_config_lacks_fields():
    assert flag_pingpong(track([A, B, A, B]), NS()) is not None
    assert flag_pingpong(track([A, A, B, A, A]), NS()) is None


def test_input_is_not_mutated(cfg):
    records = track([A, B, A, B, A])
    records.reverse()
    snapshot = list(records)
    flag_pingpong(records, cfg)
    assert records == snapshot