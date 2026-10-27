"""Decide whether a received ADS-B callsign was heard cleanly.

The spoofing rule that flags one aircraft broadcasting two callsigns fired
on radio reception errors (garbled characters shown as "?"), not on real
callsign changes. Checking readability first lets the rule ignore corrupted
receptions and only compare callsigns we can actually trust.
"""
from __future__ import annotations

__all__ = ["is_readable_callsign"]


def is_readable_callsign(callsign: str | None) -> bool:
    """Return True only if the callsign was received cleanly.

    Real ADS-B callsigns contain only A-Z and 0-9 and are padded with
    trailing spaces to 8 characters, so the padding is stripped and case is
    ignored before checking. Anything else (for example the "?" our receiver
    emits for characters it could not decode) means the reception was
    corrupted, and comparing it against another callsign would produce a
    false spoofing alert.

    A missing or blank callsign is not readable either: it means we heard
    nothing usable, not that the aircraft broadcast an empty identity, so it
    must not be treated as a clean value to compare against.
    """
    if callsign is None:
        return False

    cleaned = callsign.strip()
    # str.isalnum() accepts non-ASCII letters and digits, and some of them
    # upper-case to plain ASCII, so rule them out before anything else.
    if not cleaned or not cleaned.isascii():
        return False

    return cleaned.upper().isalnum()
