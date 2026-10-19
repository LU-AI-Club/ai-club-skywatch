"""Tests for SpoofingConfig and its to_parameters."""

from __future__ import annotations

import pytest

from air.detectors.spoofing.config import SpoofingConfig


def test_the_agreed_defaults():
    """These are the numbers in section 4 of the design doc."""
    cfg = SpoofingConfig()
    assert cfg.teleport_kt == 1000.0
    assert cfg.turn_rate_dps == 10.0
    assert cfg.speed_delta_kt == 50.0
    assert cfg.speed_delta_frac == 0.30
    assert cfg.vrate_delta_fpm == 2000.0
    assert cfg.max_gap_s == 60.0
    assert cfg.nic_floor == 1
    assert cfg.pingpong_reversals == 3


def test_a_threshold_can_be_overridden():
    """The evaluation lane sweeps limits without touching any rule."""
    assert SpoofingConfig(teleport_kt=750.0).teleport_kt == 750.0


def test_the_config_is_frozen():
    """A detection must stay interpretable next to the limits that made it."""
    with pytest.raises(Exception):
        SpoofingConfig().teleport_kt = 1.0


@pytest.mark.parametrize(
    "field", ["teleport_kt", "turn_rate_dps", "speed_delta_kt", "vrate_delta_fpm"]
)
def test_a_non_positive_threshold_is_rejected(field):
    with pytest.raises(ValueError, match=field):
        SpoofingConfig(**{field: 0.0})


@pytest.mark.parametrize("frac", [0.0, 1.0, 1.5])
def test_speed_fraction_must_be_a_real_fraction(frac):
    with pytest.raises(ValueError, match="speed_delta_frac"):
        SpoofingConfig(speed_delta_frac=frac)


def test_confidence_floor_must_be_a_probability():
    with pytest.raises(ValueError, match="min_confidence"):
        SpoofingConfig(min_confidence=1.5)


def test_the_gap_limit_must_exceed_the_minimum_pair_spacing():
    with pytest.raises(ValueError, match="max_gap_s"):
        SpoofingConfig(max_gap_s=0.1, min_dt_s=0.5)


def test_to_parameters_carries_every_setting():
    params = SpoofingConfig().to_parameters()
    assert params["teleport_kt"] == 1000.0
    assert params["max_gap_s"] == 60.0
    assert params["min_confidence"] == 0.35
    assert len(params) >= 13


def test_to_parameters_reflects_an_override():
    """What lands on the alert is what actually applied, not the default."""
    assert SpoofingConfig(teleport_kt=600.0).to_parameters()["teleport_kt"] == 600.0
