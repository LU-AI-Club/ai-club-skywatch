"""Stream C tests - geo/zone_index.py + geo/containment.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ..geo.containment import check_containment
from ..types import ExitReason
from .conftest import make_state

SKIP = pytest.mark.skip(reason="stream C: not implemented")


@SKIP
def test_flags_a_state_inside_the_polygon() -> None:
    """The default state sits inside P-901, so contained is True and penetration
    is a real distance."""
    pytest.fail('write me: load zones, assert contained is True, '
                'P-901 in zone_ids, penetration_nm is not None')


@SKIP
def test_reports_outside_polygon_when_clear() -> None:
    """A state east of KLYH hits nothing, and the result carries a reason rather
    than returning None."""
    pytest.fail('write me: make_state(lat=37.10, lon=-78.80), assert '
                'contained is False and reason is ExitReason.OUTSIDE_POLYGON')
