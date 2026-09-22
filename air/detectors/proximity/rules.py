"""The rulebook: does this pair cross a threshold, and how serious is it?

Two small functions and no math. ``flag_pair`` checks the basic gates, then
``severity_for`` looks the predicted separation up in the tier table.

EVERY NUMBER COMES FROM THE CONFIG (configs/detectors/proximity.yaml). If you
find yourself typing 120 or 0.5 into this file, read the config instead.

OWNER: CalebK (severity_for, flag_pair).
Tests: tests/air/detectors/proximity/test_proximity_rules.py
"""

from __future__ import annotations

from air.detectors.proximity.config import ProximityConfig
from air.detectors.proximity.features import PairGeometry
from contracts import SeverityLevel


def severity_for(
    predicted_horizontal_nm: float, predicted_vertical_ft: float, cfg: ProximityConfig
) -> SeverityLevel | None:
    """Look up the severity tier for a predicted separation, or None if none match.

    Walk ``cfg.tiers`` in order (HIGH first — the YAML lists them tightest to
    loosest) and return the first tier where BOTH hold:

        predicted_horizontal_nm < tier.max_horizontal_nm
        predicted_vertical_ft   < tier.max_vertical_ft

    Both must hold. 0.2 nm apart horizontally but 2000 ft apart vertically is
    normal, legal, and returns None.
    """
    raise NotImplementedError("TODO CalebK: see docstring above and the tests")


def flag_pair(geom: PairGeometry, cfg: ProximityConfig) -> SeverityLevel | None:
    """Apply the gates, then the threshold table. None means "do not emit".

    Gates, in order — fail any one and return None:
      1. ``geom.t_cpa_s`` is not None (relative velocity exists)
      2. ``geom.converging`` (closest approach is in the future, t_cpa > 0)
      3. ``geom.t_cpa_s <= cfg.max_tcpa_s`` (straight-line prediction is
         only trusted for the next couple of minutes)
      4. predicted separations are not None

    Then return ``severity_for(predicted_horizontal, predicted_vertical, cfg)``.
    """
    raise NotImplementedError("TODO CalebK: see docstring above and the tests")


__all__ = ["flag_pair", "severity_for"]
