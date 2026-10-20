"""Tests for the physics rules.

Every rule gets a case that fires and a case that does not. A rule that flags
everything passes a one-sided test and is useless.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.physics import (
    flag_nic_floor,
    flag_speed_delta,
    flag_subterrain,
    flag_teleport,
    flag_turn_rate,
    flag_vrate_delta,
    speed_delta_limit_kt,
    speed_position_error_kt,
    subterrain_depth_ft,
    vrate_quantisation_fpm,
)
from air.detectors.spoofing.records import SpoofingFeatureRecord
from air.models.observation import AdsbObservation

CFG = SpoofingConfig()
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


def obs(seconds: float, nic: int | None = None) -> AdsbObservation:
    return AdsbObservation(
        icao24="a1b2c3",
        observed_at=T0 + timedelta(seconds=seconds),
        latitude=37.0,
        longitude=-79.0,
        nic=nic,
    )


# --- flag_teleport -----------------------------------------------------------
def test_teleport_fires_on_impossible_speed():
    assert flag_teleport(record(implied_speed_kt=21_285.0), CFG) == "TELEPORT"


def test_teleport_ignores_a_jet_stream_tailwind():
    """780 kt over the ground is fast and entirely real."""
    assert flag_teleport(record(implied_speed_kt=780.0), CFG) is None


def test_teleport_is_strictly_greater_than_the_limit():
    assert flag_teleport(record(implied_speed_kt=1000.0), CFG) is None


def test_teleport_abstains_without_a_speed():
    assert flag_teleport(record(implied_speed_kt=None), CFG) is None


def test_teleport_abstains_on_a_very_short_gap():
    """Below min_dt_s, timestamp error dominates the arithmetic."""
    assert flag_teleport(record(dt_s=0.2, implied_speed_kt=50_000.0), CFG) is None


# --- flag_turn_rate ----------------------------------------------------------
def test_turn_rate_fires_on_an_aerobatic_turn():
    assert flag_turn_rate(record(turn_rate_dps=19.0), CFG) == "IMPOSSIBLE_TURN"


def test_turn_rate_fires_the_same_turning_left():
    """Turn rate is signed; the rule compares magnitude."""
    assert flag_turn_rate(record(turn_rate_dps=-19.0), CFG) == "IMPOSSIBLE_TURN"


def test_turn_rate_ignores_a_standard_rate_turn():
    assert flag_turn_rate(record(turn_rate_dps=3.0), CFG) is None


def test_turn_rate_abstains_without_a_heading():
    assert flag_turn_rate(record(turn_rate_dps=None), CFG) is None


# --- flag_speed_delta --------------------------------------------------------
def test_speed_delta_fires_when_the_claim_contradicts_the_positions():
    hit = flag_speed_delta(
        record(reported_speed_kt=300.0, speed_delta_kt=150.0), CFG
    )
    assert hit == "SPEED_DISAGREEMENT"


def test_speed_delta_ignores_ordinary_wind_and_sensor_error():
    assert flag_speed_delta(record(reported_speed_kt=450.0, speed_delta_kt=30.0), CFG) is None


def test_the_limit_scales_with_the_aircraft():
    """A fixed margin alone is wrong for both a trainer and a jet."""
    slow = record(reported_speed_kt=90.0)
    fast = record(reported_speed_kt=500.0)
    allowance = speed_position_error_kt(slow, CFG)
    assert speed_delta_limit_kt(slow, CFG) == 50.0 + allowance    # the floor wins
    assert speed_delta_limit_kt(fast, CFG) == 150.0 + allowance   # 30% wins


def test_speed_delta_abstains_without_a_reported_speed():
    assert flag_speed_delta(record(speed_delta_kt=None), CFG) is None


def test_speed_delta_ignores_position_error_at_a_short_gap():
    """SPOOF-1: a few metres of error over half a second is not a speed lie.

    The real-data case "a92abb: 0.0 nm in 0.55 s" -- 44 m covered where 228 kt
    predicts 65 m, so the positions imply 156 kt against a claimed 228.
    """
    jitter = record(dt_s=0.553, reported_speed_kt=228.0, speed_delta_kt=-72.0)
    assert flag_speed_delta(jitter, CFG) is None


def test_a_real_speed_lie_at_a_short_gap_still_fires():
    """The allowance is bounded: claiming 100 kt while covering 450 kt fires."""
    assert flag_speed_delta(
        record(dt_s=0.55, reported_speed_kt=100.0, speed_delta_kt=350.0), CFG
    ) is not None


def test_the_speed_allowance_shrinks_as_the_gap_grows():
    """2 x 30 m of position error, expressed as speed over the gap."""
    assert speed_position_error_kt(record(dt_s=0.55), CFG) == pytest.approx(212.1, abs=0.1)
    assert speed_position_error_kt(record(dt_s=5.0), CFG) == pytest.approx(23.3, abs=0.1)
    assert speed_position_error_kt(record(dt_s=30.0), CFG) == pytest.approx(3.9, abs=0.1)


def test_a_modest_speed_disagreement_over_a_long_gap_fires():
    """A long gap makes position error negligible, so 32% off is caught."""
    assert flag_speed_delta(
        record(dt_s=10.0, reported_speed_kt=306.0, speed_delta_kt=144.0), CFG
    ) is not None


# --- flag_vrate_delta --------------------------------------------------------
def test_vrate_delta_fires_on_a_claimed_climb_that_did_not_happen():
    assert flag_vrate_delta(record(vrate_delta_fpm=3500.0), CFG) == "VRATE_DISAGREEMENT"


def test_vrate_delta_ignores_a_legal_steep_descent():
    """-3000 fpm where the altitudes agree is ordinary."""
    assert flag_vrate_delta(record(vrate_delta_fpm=-100.0), CFG) is None


def test_vrate_delta_abstains_without_an_altitude():
    assert flag_vrate_delta(record(vrate_delta_fpm=None), CFG) is None


def test_vrate_delta_ignores_the_altitude_step_artefact():
    """A level aircraft stepping one 25 ft bucket in 0.55 s implies 2,727 fpm.

    Nothing is climbing; the feed just rounds altitude. This single artefact
    produced 96% of all alerts on an hour of real data before the rule
    allowed for it.
    """
    artefact = record(dt_s=0.55, vrate_delta_fpm=2_727.0)
    assert flag_vrate_delta(artefact, CFG) is None


def test_a_real_disagreement_at_a_short_gap_still_fires():
    """The allowance must not swallow a genuine contradiction."""
    assert flag_vrate_delta(record(dt_s=0.55, vrate_delta_fpm=12_000.0), CFG) is not None


def test_the_allowance_shrinks_as_the_gap_grows():
    """A longer gap is more trustworthy, so the rule gets stricter."""
    assert vrate_quantisation_fpm(record(dt_s=1.0), CFG) == 3_000.0
    assert vrate_quantisation_fpm(record(dt_s=10.0), CFG) == 300.0
    assert vrate_quantisation_fpm(record(dt_s=60.0), CFG) == 50.0


def test_a_modest_disagreement_over_a_long_gap_fires():
    """At 10 s the allowance is only 300 fpm, so 2,500 is a real finding."""
    assert flag_vrate_delta(record(dt_s=10.0, vrate_delta_fpm=2_500.0), CFG) is not None


# --- flag_nic_floor ----------------------------------------------------------
def test_nic_floor_fires_on_a_sustained_collapse():
    segment = [obs(i * 10, nic=0) for i in range(8)]       # 70 s at the floor
    assert flag_nic_floor(segment, CFG) == "INTEGRITY_FLOOR"


def test_nic_floor_ignores_a_brief_dip():
    """20 s down then recovery is ordinary equipment behaviour."""
    segment = [obs(0, 8), obs(10, 1), obs(20, 1), obs(30, 8), obs(40, 8)]
    assert flag_nic_floor(segment, CFG) is None


def test_nic_floor_ignores_healthy_integrity():
    assert flag_nic_floor([obs(i * 10, nic=8) for i in range(8)], CFG) is None


def test_nic_floor_abstains_on_a_track_too_short_to_show_duration():
    assert flag_nic_floor([obs(0, 0)], CFG) is None


def test_nic_floor_abstains_when_integrity_is_not_reported():
    assert flag_nic_floor([obs(i * 10) for i in range(8)], CFG) is None


# --- flag_subterrain ---------------------------------------------------------
def test_subterrain_fires_below_the_ground():
    hit = flag_subterrain(record(altitude_ft=500.0), 800.0, CFG)
    assert hit == "BELOW_TERRAIN"


def test_subterrain_ignores_an_aircraft_above_the_ground():
    assert flag_subterrain(record(altitude_ft=5000.0), 800.0, CFG) is None


def test_subterrain_abstains_without_elevation_data():
    """Assuming sea level would flag every approach to a mountain airport."""
    assert flag_subterrain(record(altitude_ft=500.0), None, CFG) is None


def test_depth_is_reported_as_a_positive_number():
    """Events store measured as a positive value: 300 means 300 ft under."""
    assert subterrain_depth_ft(record(altitude_ft=500.0), 800.0) == 300.0
    assert subterrain_depth_ft(record(altitude_ft=5000.0), 800.0) is None
