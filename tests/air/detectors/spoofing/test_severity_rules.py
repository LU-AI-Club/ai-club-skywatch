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


@pytest.mark.parametrize("gate", ["turn_rate_v1", "identity_drift_v1"])
def test_noisy_gates_are_low(gate):
    assert severity_weight(gate) <= 0.4


def test_teleport_outweighs_turn_rate():
    assert severity_weight("teleport_v1") > severity_weight("turn_rate_v1")


def test_ordering_strong_then_high_then_low():
    assert (
        severity_weight("teleport_v1")
        >= severity_weight("impersonation_v1")
        > severity_weight("identity_drift_v1")
    )