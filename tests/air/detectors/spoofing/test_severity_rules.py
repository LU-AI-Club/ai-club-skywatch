import pytest

from air.detectors.spoofing.severity_rules import (
    DEFAULT_WEIGHT,
    SEVERITY_WEIGHTS,
    severity_weight,
)


@pytest.mark.parametrize("gate", list(SEVERITY_WEIGHTS))
def test_known_gates_are_between_zero_and_one(gate):
    assert 0.0 <= severity_weight(gate) <= 1.0


def test_unknown_gate_returns_default():
    assert severity_weight("not_a_real_gate_v1") == 0.5
    assert severity_weight("not_a_real_gate_v1") == DEFAULT_WEIGHT


def test_empty_gate_returns_default():
    assert severity_weight("") == DEFAULT_WEIGHT


@pytest.mark.parametrize("gate", ["teleport_v1", "coexistence_v1"])
def test_strongest_gates_are_near_one(gate):
    assert severity_weight(gate) >= 0.9


@pytest.mark.parametrize("gate", ["registry_mismatch_v1", "impersonation_v1"])
def test_registry_and_impersonation_are_high(gate):
    assert 0.7 <= severity_weight(gate) < 0.9


@pytest.mark.parametrize("gate", ["identity_drift_v1"])
def test_weak_evidence_gates_are_low(gate):
    assert severity_weight(gate) <= 0.4


def test_turn_rate_sits_between_weak_and_near_certain():
    """Recalibrated when flag_turn_rate gained its minimum-speed gate.

    It was 0.2 while the rule fired on taxiing aircraft and about half its
    alerts were noise, which capped it below MEDIUM at any score. It now
    abstains below flying speed, so a hit means an aircraft at cruise
    reporting a turn no airframe can fly: real evidence, though heading is
    noisier than position, so it stays under teleport and coexistence.
    """
    weight = severity_weight("turn_rate_v1")
    assert severity_weight("identity_drift_v1") < weight
    assert weight < severity_weight("teleport_v1")


def test_teleport_outweighs_turn_rate():
    assert severity_weight("teleport_v1") > severity_weight("turn_rate_v1")


def test_ordering_strong_then_high_then_low():
    assert (
        severity_weight("teleport_v1")
        >= severity_weight("impersonation_v1")
        > severity_weight("identity_drift_v1")
    )