"""Stream G tests - logic/scoring.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ...air.detectors.no_fly_zone.logic.scoring import build_detection
from ...air.detectors.no_fly_zone.types import Severity

SKIP = pytest.mark.skip(reason="stream G: not implemented")


@SKIP
def test_prohibited_incursion_scores_high() -> None:
    """PROHIBITED bases at 0.9 with no context signals, and the Detection pins the
    airspace cycle into baseline_or_model_version."""
    pytest.fail('write me: assert anomaly_score >= 0.9 and '
                'baseline_or_model_version ends with sua-2026-08-07')


@SKIP
def test_unknown_activation_caps_severity() -> None:
    """A NOTAM zone we could not resolve is capped at severity.unknown_activation_cap
    and never reported as a confirmed incursion."""
    pytest.fail('write me: activation UNKNOWN, assert severity is Severity.LOW')
