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
    ``icao24`` inside a configured military ICAO24 range.
``lifeguard_callsign``
    Callsign prefixed LIFEGUARD / MEDEVAC / AIR EVAC / HOSP.
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

_EMERGENCY_SQUAWKS: frozenset[str] = frozenset({"7500", "7600", "7700"})
# 7500 is unlawful interference, 7600 is lost comms, 7700 is emergency.
_NON_DISCRETE_SQUAWKS: frozenset[str] = frozenset({"1200"}) # 1200 is the VFR default squawk in the US, and is not a discrete code. This will have to be expanded once the region is expanded.
# can be replaced with non_discrete_squawks = cfg["squawks"]["non_discrete"] if the YAML is updated to include a list of regional non-disscrete codes.
_LIFEGUARD_PREFIXES: tuple[str, ...] = ("LIFEGUARD", "MEDEVAC", "AIREVAC", "HOSP")


def _normalize_squawk(squawk: str | int |None) -> str | None:
    """Normalize and validate a four-digit octal squawk code."""
    if squawk is None:
        return None
    normalized = str(squawk).strip().zfill(4)  # pad to four digits
    if len(normalized) != 4 or any(
        digit not in "01234567" for digit in normalized
    ):
        return None
    return normalized


def gather_signals(state: AircraftState, cfg: Config) -> list[ContextSignal]:
    """Collect the authorization-context signals present in ``state``."""
    weights = cfg["scoring"]["context_weights"]
    signals: list[ContextSignal] = []

    squawk = _normalize_squawk(state.squawk)

    if squawk in _EMERGENCY_SQUAWKS:
        signals.append(ContextSignal(
            name="emergency_squawk",
            weight=weights["emergency_squawk"],
            fact=f"squawk {squawk} is an emergency code",
        ))
    elif squawk and squawk not in _NON_DISCRETE_SQUAWKS: 
        signals.append(ContextSignal(
            name="atc_discrete_squawk",
            weight=weights["atc_discrete_squawk"],
            fact=f"squawk {squawk} is a discrete beacon code",
        ))

    callsign = (state.callsign or "").strip().upper()
    if callsign.startswith(_LIFEGUARD_PREFIXES):
        medical_prefix = next(
            prefix for prefix in _LIFEGUARD_PREFIXES if callsign.startswith(prefix)
        )
        signals.append(ContextSignal(
            name="lifeguard_callsign",
            weight=weights["lifeguard_callsign"],
            fact=f"callsign {callsign!r} starts with a medical-flight prefix {medical_prefix!r}",
        ))

    icao24 = state.icao24.strip().upper()
    if len(icao24) == 6 and all(
        digit in "0123456789ABCDEF" for digit in icao24
    ):
        address = int(icao24, 16)
        for first_hex, last_hex in cfg["airspace"]["military_icao24_ranges"]: # needs to be provided by the YAML file
            first_address = int(first_hex, 16)
            last_address = int(last_hex, 16)
            if first_address <= address <= last_address:
                signals.append(ContextSignal(
                    name="military_hex",
                    weight=weights["military_hex"],
                    fact=(
                        f"icao24 {icao24} is in configured military ICAO24 "
                        f"range {first_hex.upper()}-{last_hex.upper()}"
                    ),
                ))
                break

    return signals
