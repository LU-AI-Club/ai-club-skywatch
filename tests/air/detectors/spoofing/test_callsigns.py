"""Tests for is_readable_callsign, which filters out garbled ADS-B callsigns."""
from __future__ import annotations

import pytest

from air.detectors.spoofing.callsigns import is_readable_callsign


@pytest.mark.parametrize(
    "callsign",
    [
        "AAL1715",  # normal callsign
        "AAL36  ",  # padded with trailing spaces, as broadcast
        "aal36",  # lowercase is accepted
        "VXP468",  # real capture, aircraft aafa0d
        "MXY909",  # real capture, aircraft a1f77c
    ],
)
def test_clean_callsigns_are_readable(callsign: str) -> None:
    assert is_readable_callsign(callsign) is True


@pytest.mark.parametrize(
    "callsign",
    [
        "VXP?29T3",  # real capture, aircraft aafa0d
        "?FD5IFT?",  # real capture, aircraft a1f77c
        "AAL-1715",  # hyphen
        "AAL.1715",  # dot
    ],
)
def test_corrupted_or_invalid_characters_are_not_readable(callsign: str) -> None:
    assert is_readable_callsign(callsign) is False


@pytest.mark.parametrize("callsign", [None, "", "   "])
def test_missing_or_blank_callsigns_are_not_readable(callsign: str | None) -> None:
    assert is_readable_callsign(callsign) is False
