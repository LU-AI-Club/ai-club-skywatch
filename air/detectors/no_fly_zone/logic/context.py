"""Stream F - signals that make an incursion look authorized.

Most aircraft inside restricted airspace belong there. A military jet in its
own MOA, a medevac flight, an aircraft under ATC control on a discrete squawk,
or one declaring an emergency are all ordinary. These signals *lower* the
score. They never prove approval, and they must never zero a detection out.

Inputs
------
state:
    Supplies ``squawk``, ``icao24``, ``callsign`` and ``emitter_category``.
cfg:
    Supplies ``scoring.context_weights``. Weights are config, never literals in
    this module.

Outputs
-------
A list of :class:`ContextSignal`, one per signal observed, each carrying the
weight read from config and a deterministic human-readable ``fact``. An empty
list is the common case and is not a failure.

Signals to implement (keys must match ``scoring.context_weights``)
------------------------------------------------------------------
``atc_discrete_squawk``
    A discrete beacon code rather than a VFR conspicuity code: the aircraft is
    talking to someone.
``military_hex``
    ``icao24`` inside a published military allocation block.
``lifeguard_callsign``
    Callsign prefixed LIFEGUARD / MEDEVAC / HOSP.
``emergency_squawk``
    7500, 7600 or 7700.

Failure causes
--------------
KeyError
    A signal name has no matching entry in ``scoring.context_weights``. Fail
    loudly: a silently unweighted signal would quietly skew every score.

Notes
-----
Every ``fact`` must be reproducible from the state alone. No inference about
intent, ever - this detector reports deviation, not motive.
"""
from __future__ import annotations

from ..config import Config
from ..types import AircraftState, ContextSignal

# These are definitions, not tunables: the codes and prefixes mean what they
# mean by regulation or convention. The weights they carry come from config.
_EMERGENCY_SQUAWKS = {
    "7500": "unlawful interference",
    "7600": "radio failure",
    "7700": "general emergency",
}
# Codes that do not identify one aircraft to a controller: VFR (1200), the
# IFR non-discrete code (2000), fire fighting (1255), search and rescue (1277),
# the ICAO VFR code (7000), and an unset transponder (0000).
_NON_DISCRETE_SQUAWKS = {"0000", "1200", "1255", "1277", "2000", "7000"}
_LIFEGUARD_PREFIXES = ("LIFEGUARD", "MEDEVAC", "HOSP")
# US military ICAO 24-bit addresses: ADF7C8-AFFFFF, the block tar1090 and
# readsb use for their military filter.
_MILITARY_HEX_BLOCKS = ((0xADF7C8, 0xAFFFFF),)


def gather_signals(state: AircraftState, cfg: Config) -> list[ContextSignal]:
    """Collect the authorization-context signals present in ``state``.

    Raises:
        KeyError: A signal has no entry in ``scoring.context_weights``.
    """
    weights = cfg["scoring"]["context_weights"]

    def signal(name: str, fact: str) -> ContextSignal:
        if name not in weights:
            raise KeyError(f"scoring.context_weights has no weight for signal {name!r}")
        return ContextSignal(name=name, weight=float(weights[name]), fact=fact)

    signals: list[ContextSignal] = []
    squawk = (state.squawk or "").strip()
    if squawk in _EMERGENCY_SQUAWKS:
        signals.append(signal(
            "emergency_squawk",
            f"Squawking {squawk} ({_EMERGENCY_SQUAWKS[squawk]}).",
        ))
    elif _is_discrete(squawk):
        signals.append(signal(
            "atc_discrete_squawk",
            f"Squawking discrete code {squawk}, which suggests contact with ATC.",
        ))

    if _is_military_hex(state.icao24):
        signals.append(signal(
            "military_hex",
            f"ICAO address {state.icao24} is in the US military allocation block.",
        ))

    callsign = (state.callsign or "").strip().upper()
    if callsign.startswith(_LIFEGUARD_PREFIXES):
        signals.append(signal(
            "lifeguard_callsign",
            f"Callsign {callsign} marks a medical flight.",
        ))
    return signals


def _is_discrete(squawk: str) -> bool:
    """A four-digit octal beacon code that is not one of the shared codes."""
    octal = len(squawk) == 4 and set(squawk) <= set("01234567")
    return octal and squawk not in _NON_DISCRETE_SQUAWKS and squawk not in _EMERGENCY_SQUAWKS


def _is_military_hex(icao24: str) -> bool:
    try:
        value = int(icao24, 16)
    except ValueError:
        return False
    return any(low <= value <= high for low, high in _MILITARY_HEX_BLOCKS)
