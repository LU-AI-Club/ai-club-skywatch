"""Stream D tests - geo/altitude.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ...air.detectors.no_fly_zone.geo.altitude import vertical_check
from ...air.detectors.no_fly_zone.types import AltitudeSource, ExitReason
from .conftest import make_state

SKIP = pytest.mark.skip(reason="stream D: not implemented")


@SKIP
def test_altitude_inside_the_band_is_within() -> None:
    """5200 ft geometric against P-901's SFC-18000 band is inside, and the result
    records that geometric altitude was the value compared."""
    pytest.fail('write me: assert within is True and altitude_source is '
                'AltitudeSource.GEOMETRIC')


@SKIP
def test_abstains_when_both_altitudes_are_missing() -> None:
    """No altitude means abstain with BAD_INPUT. Never guess an altitude."""
    pytest.fail('write me: make_state(alt_baro_ft=None, alt_geom_ft=None), '
                'assert reason is ExitReason.BAD_INPUT')
