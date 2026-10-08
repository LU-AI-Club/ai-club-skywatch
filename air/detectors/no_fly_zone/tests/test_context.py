"""Tests for authorization-context signals in logic/context.py."""
from __future__ import annotations

import pytest

from ..logic.context import gather_signals
from .conftest import Config, make_state


@pytest.mark.parametrize("squawk", ["7500", "7600", "7700", 7700])
def test_emergency_squawk_produces_weighted_signal(squawk: str | int, cfg: Config) -> None:
    signals = gather_signals(make_state(squawk=squawk), cfg)

    # Exactly one signal: an emergency code must not also count as discrete.
    assert len(signals) == 1
    assert signals[0].name == "emergency_squawk"
    assert signals[0].weight == cfg["scoring"]["context_weights"]["emergency_squawk"]


@pytest.mark.parametrize("squawk", ["0456", 456])
def test_discrete_squawk_produces_weighted_signal(squawk: str | int, cfg: Config) -> None:
    signals = gather_signals(make_state(squawk=squawk), cfg)

    assert len(signals) == 1
    assert signals[0].name == "atc_discrete_squawk"
    assert signals[0].weight == cfg["scoring"]["context_weights"]["atc_discrete_squawk"]


@pytest.mark.parametrize(
    ("icao24", "is_military"),
    [
        ("ADFFFF", False),  # one below the range
        ("AE0000", True),   # first address
        ("AE1234", True),
        ("AFFFFF", True),   # last address
        ("B00000", False),  # one above the range
        ("A00000", False),
        ("ZZZZZZ", False),  # malformed hex must not crash
    ],
)
def test_military_icao24_range_is_inclusive(
    icao24: str, is_military: bool, cfg: Config
) -> None:
    signals = gather_signals(make_state(icao24=icao24), cfg)

    military_signals = [signal for signal in signals if signal.name == "military_hex"]
    assert bool(military_signals) is is_military
    if is_military:
        assert military_signals[0].weight == cfg["scoring"]["context_weights"]["military_hex"]
        assert "configured military ICAO24 range" in military_signals[0].fact


@pytest.mark.parametrize("callsign", ["LIFEGUARD1", "MEDEVAC1", "AIREVAC1", "HOSP1", " airevac1 "])
def test_medical_callsign_prefix_produces_weighted_signal(callsign: str, cfg: Config) -> None:
    signals = gather_signals(make_state(callsign=callsign), cfg)

    assert len(signals) == 1
    assert signals[0].name == "lifeguard_callsign"
    assert signals[0].weight == cfg["scoring"]["context_weights"]["lifeguard_callsign"]


@pytest.mark.parametrize("callsign", ["AAL1715", "N400TG", "", None])
def test_non_medical_callsign_produces_no_signal(callsign: str | None, cfg: Config) -> None:
    assert gather_signals(make_state(callsign=callsign), cfg) == []


def test_ordinary_vfr_state_produces_no_signals(cfg: Config) -> None:
    assert gather_signals(make_state(), cfg) == []


@pytest.mark.parametrize("squawk", ["", "0", "0000", "1200", "8888", None])
def test_non_discrete_or_invalid_squawk_produces_no_signal(squawk: str | None, cfg: Config) -> None:
    assert gather_signals(make_state(squawk=squawk), cfg) == []


def test_independent_signals_all_fire_together(cfg: Config) -> None:
    state = make_state(icao24="AE1234", callsign="MEDEVAC1", squawk="4321")

    names = {signal.name for signal in gather_signals(state, cfg)}

    assert names == {"military_hex", "lifeguard_callsign", "atc_discrete_squawk"}


def test_missing_weight_key_raises_keyerror(cfg: Config) -> None:
    del cfg["scoring"]["context_weights"]["emergency_squawk"]

    with pytest.raises(KeyError):
        gather_signals(make_state(squawk="7700"), cfg)