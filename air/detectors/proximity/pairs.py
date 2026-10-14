"""Candidate pairs: which aircraft are even worth comparing at one instant?

Comparing every aircraft with every other is O(n^2) — 900 aircraft is 400,000
pairs per second. Almost all of them are hundreds of miles apart. So we drop
aircraft into lat/lon grid cells and only compare pairs in the same or a
neighbouring cell, then throw out pairs that the cheap checks rule out before
any real math happens.

OWNER: CalebG (is_airborne, candidate_pairs). cell_of is done.
"""

from __future__ import annotations

import math
from itertools import combinations

from air.detectors.proximity.config import ProximityConfig
from air.models.observation import AdsbObservation


def cell_of(obs: AdsbObservation, cell_size_deg: float) -> tuple[int, int]:
    """DONE. Integer grid cell for an observation, e.g. (74, -159) at 0.5 deg."""
    return math.floor(obs.latitude / cell_size_deg), math.floor(obs.longitude / cell_size_deg)


def is_airborne(obs: AdsbObservation, cfg: ProximityConfig) -> bool:
    """True if we believe this aircraft is flying.

    ``AdsbObservation`` has no on_ground flag, and even when ADS-B broadcasts
    one it is not always set correctly, so use the backup rule from the plan:

        on the ground  <=>  altitude_ft < cfg.ground_altitude_ft
                            AND ground_speed_kt < cfg.ground_speed_kt

    Missing altitude or missing speed -> we cannot tell -> return False
    (abstain: a pair we cannot judge must not produce a detection).
    """
    raise NotImplementedError("TODO CalebG: see docstring above and the tests")


def candidate_pairs(
    snapshot: list[AdsbObservation], cfg: ProximityConfig
) -> list[tuple[AdsbObservation, AdsbObservation]]:
    """All pairs from one instant that survive the cheap filters.

    ``snapshot`` is every aircraft's observation at ONE grid tick (see
    ``tracks.align_tracks``). Return ``(a, b)`` tuples, each unordered pair
    appearing once, with ``a.icao24 < b.icao24`` so output is deterministic.

    Keep a pair only if ALL of these hold:
      1. both are airborne (``is_airborne``)
      2. both have ``track_deg`` and ``ground_speed_kt`` (no velocity -> no
         prediction possible -> abstain)
      3. they are in the same grid cell or cells that touch, including
         diagonally (use ``cell_of``; neighbouring means each of the two cell
         indices differs by at most 1)
      4. |altitude_a - altitude_b| <= cfg.max_vertical_prefilter_ft
      5. different icao24 (an aircraft heard twice is not a conflict)

    Suggested shape: build ``{cell: [obs, ...]}`` once, then for each obs look
    up the 9 cells around it. ``itertools.combinations`` is handy for the
    within-cell pairs.
    """
    raise NotImplementedError("TODO CalebG: see docstring above and the tests")


__all__ = ["candidate_pairs", "cell_of", "is_airborne"]
