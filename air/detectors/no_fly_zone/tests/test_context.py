"""Stream F tests - logic/context.py."""
from __future__ import annotations

from ..config import Config
from ..logic.context import gather_signals
from .conftest import make_state


def test_emergency_squawk_produces_a_weighted_signal(cfg: Config) -> None:
    """7700 yields one signal whose weight comes from config, not a literal."""
    signals = gather_signals(make_state(squawk="7700"), cfg)
    assert [s.name for s in signals] == ["emergency_squawk"]
    assert signals[0].weight == cfg["scoring"]["context_weights"]["emergency_squawk"]


def test_ordinary_state_produces_no_signals(cfg: Config) -> None:
    """A VFR squawk on a civil airframe yields an empty list, which is the normal
    case and not a failure."""
    assert gather_signals(make_state(), cfg) == []


def test_discrete_military_and_lifeguard_signals(cfg: Config) -> None:
    state = make_state(squawk="4521", icao24="ae1234", callsign="LIFEGUARD1")
    names = {s.name for s in gather_signals(state, cfg)}
    assert names == {"atc_discrete_squawk", "military_hex", "lifeguard_callsign"}
