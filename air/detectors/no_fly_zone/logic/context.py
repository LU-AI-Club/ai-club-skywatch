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


def gather_signals(state: AircraftState, cfg: Config) -> list[ContextSignal]:
    """Collect the authorization-context signals present in ``state``."""
    raise NotImplementedError("stream F: context")
