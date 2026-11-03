"""Spine component A — read canonical observations as AdsbObservations.

OWNER: Spoofing team (see docs/live_integration/TEAM_SPOOFING.md).

This is the single source of truth for turning rows in the `observations` table
into the detectors' input contract. It owns the `payload` JSON parsing so no two
teams parse it differently. No other team touches SQL or `payload` here — they
call `read_window`.

The signature below is FROZEN (the contract the runner and tests build against).
The body is a stub: the Spoofing team fills it in. Do not change the signature
without announcing it to the Proximity (B) and No-Fly-Zone (C) teams, who import
it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from air.models.observation import AdsbObservation


def read_window(
    conn: Any,
    *,
    start: datetime,
    end: datetime,
    domain: str = "air",
) -> list[AdsbObservation]:
    """Return the observations in ``[start, end)`` as ``AdsbObservation``s.

    Parameters
    ----------
    conn:
        A live database connection (psycopg). Passed in by the runner; never
        opened here.
    start, end:
        Window bounds, tz-aware UTC. Half-open: ``start`` inclusive, ``end``
        exclusive.
    domain:
        Observation domain to read; ``"air"`` for ADS-B.

    Behavior the implementation must provide
    ----------------------------------------
    * Windowed query on ``observed_at`` filtered to ``domain``, using the
      ``(entity_id, observed_at)`` index.
    * Map columns -> ``AdsbObservation``: ``sog`` -> ``ground_speed_kt``,
      ``cog`` -> ``track_deg``; pull ``altitude_ft``, ``alt_geom_ft``,
      ``vertical_rate_fpm``, ``nic``, ``nacp``, ``squawk``, ``callsign``,
      ``emitter_category``, ``on_ground`` out of the ``payload`` JSON.
    * Abstain (skip) on any row that cannot form a valid ``AdsbObservation``;
      never guess a missing field.
    * Pure read: no writes, no detector logic.
    """
    raise NotImplementedError("Spine A: Spoofing team — see docs/live_integration/TEAM_SPOOFING.md")


__all__ = ["read_window"]
