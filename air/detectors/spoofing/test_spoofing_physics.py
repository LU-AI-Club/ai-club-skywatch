"""Tests for air/detectors/spoofing/config.py and physics.py.

Values are typed straight into the test, per the worksheet's example.
Once pos_*/neg_* fixtures flow through build_features, add fixture-
based versions alongside these (see pos_teleport.json /
neg_tailwind_cruise.json etc. in air/fixtures/spoofing/).
"""

from types import SimpleNamespace

from air.detectors.spoofing.config import SpoofingConfig, to_parameters
from air.detectors.spoofing.physics import (
    flag_teleport,
    flag_turn_rate,
    flag_speed_delta,
    flag_vrate_delta,
    flag_nic_floor,
)


# ---- config -----------------------------------------------------------

def test_to_parameters_returns_all_limits():
    params = to_parameters(SpoofingConfig())
    assert params == {
        "teleport_kt": 1000.0,
        "turn_rate_deg_s": 10.0,
        "speed_delta_kt": 50.0,
        "speed_delta_pct": 0.30,
        "vrate_delta_fpm": 2000.0,
        "nic_floor_s": 60.0,
    }


# ---- flag_teleport ------------------------------------------------------

def test_teleport_fires():
    record = SimpleNamespace(implied_speed_kt=21285.0)
    assert flag_teleport(record, SpoofingConfig()) == "TELEPORT"


def test_tailwind_does_not_fire():
    record = SimpleNamespace(implied_speed_kt=780.0)
    assert flag_teleport(record, SpoofingConfig()) is None


# ---- flag_turn_rate -------------------------------------------------

def test_impossible_turn_fires():
    record = SimpleNamespace(turn_rate_deg_s=45.0)
    assert flag_turn_rate(record, SpoofingConfig()) == "TURN_RATE"


def test_standard_turn_does_not_fire():
    record = SimpleNamespace(turn_rate_deg_s=3.0)
    assert flag_turn_rate(record, SpoofingConfig()) is None


# ---- flag_speed_delta -------------------------------------------------

def test_speed_contradiction_fires():
    record = SimpleNamespace(claimed_speed_kt=250.0, implied_speed_kt=480.0)
    assert flag_speed_delta(record, SpoofingConfig()) == "SPEED_DELTA"


def test_clean_track_speed_does_not_fire():
    record = SimpleNamespace(claimed_speed_kt=460.0, implied_speed_kt=470.0)
    assert flag_speed_delta(record, SpoofingConfig()) is None


# ---- flag_vrate_delta -------------------------------------------------

def test_vrate_contradiction_fires():
    record = SimpleNamespace(claimed_vrate_fpm=0.0, implied_vrate_fpm=5000.0)
    assert flag_vrate_delta(record, SpoofingConfig()) == "VRATE_DELTA"


def test_legal_descent_does_not_fire():
    record = SimpleNamespace(claimed_vrate_fpm=-1800.0, implied_vrate_fpm=-1600.0)
    assert flag_vrate_delta(record, SpoofingConfig()) is None


# ---- flag_nic_floor -----------------------------------------------------

def test_integrity_collapse_fires():
    segment = [
        SimpleNamespace(nic=1, timestamp=0.0),
        SimpleNamespace(nic=0, timestamp=20.0),
        SimpleNamespace(nic=1, timestamp=40.0),
        SimpleNamespace(nic=0, timestamp=65.0),
    ]
    assert flag_nic_floor(segment, SpoofingConfig()) == "NIC_FLOOR"


def test_brief_nic_dip_does_not_fire():
    segment = [
        SimpleNamespace(nic=8, timestamp=0.0),
        SimpleNamespace(nic=1, timestamp=10.0),
        SimpleNamespace(nic=8, timestamp=20.0),
    ]
    assert flag_nic_floor(segment, SpoofingConfig()) is None
