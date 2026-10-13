"""Stream J tests - dashboard/app.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import pytest

from ..dashboard import app

SKIP = pytest.mark.skip(reason="stream J: not implemented")


@SKIP
def test_importing_the_app_does_no_io() -> None:
    """The module imports cleanly with no data files present - the Streamlit body
    stays guarded behind __main__."""
    assert hasattr(app, 'main')


@SKIP
def test_missing_detections_file_shows_an_empty_state() -> None:
    """A run that has not happened yet renders an empty state naming the expected
    path, not a stack trace."""
    pytest.fail('write me: point the app at a missing file, assert no raise')
