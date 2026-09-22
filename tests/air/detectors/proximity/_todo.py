"""The progress board.

A test decorated ``@todo("Erik")`` is EXPECTED to fail with NotImplementedError
until Erik fills in the function. pytest reports it as ``x`` (xfail), not as a
red failure, so CI stays green while work is in progress.

The moment the function is implemented:
  * correct   -> the test passes and pytest reports ``X`` (XPASS)
  * incorrect -> a real red failure (any error other than NotImplementedError)

When your tests XPASS, delete the ``@todo`` line from them in the same PR.
See which are still open with:   pytest tests/air/detectors/proximity -q -rxX
"""

from __future__ import annotations

import pytest


def todo(owner: str):
    return pytest.mark.xfail(raises=NotImplementedError, reason=f"TODO {owner}", strict=False)
