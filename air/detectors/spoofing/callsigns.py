"""Decide whether a received ADS-B callsign was heard cleanly.

The spoofing rule that flags one aircraft broadcasting two callsigns fired
on radio reception errors (garbled characters shown as "?"), not on real
callsign changes. Checking readability first lets the rule ignore corrupted
receptions and only compare callsigns we can actually trust.
"""
from __future__ import annotations

import re

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

# An ICAO flight callsign is a three-letter airline designator followed by the
# flight number: AAL1478, SAS926, RPA5645. A trailing letter is allowed, as in
# AAL123A. General-aviation aircraft broadcast their registration instead
# (N784LU, G-ABCD), which has no operator in it and does not match.
_FLIGHT_CALLSIGN = re.compile(r"^([A-Z]{3})(\d{1,4})([A-Z]?)$")


def operator_prefix(callsign: str | None) -> str | None:
    """The airline that a flight callsign belongs to, or None.

    None means the question does not apply -- a registration, or something we
    cannot parse -- not that the operator is unknown. Callers must treat those
    two differently: two registrations on one address is suspicious, whereas
    two flight numbers from one airline is Tuesday.
    """
    if not is_readable_callsign(callsign):
        return None
    match = _FLIGHT_CALLSIGN.match(str(callsign).strip().upper())
    return match.group(1) if match else None


def is_same_operator(first: str | None, second: str | None) -> bool:
    """Do these two callsigns belong to the same airline?

    False whenever either side has no operator to compare -- a registration or
    an unparseable callsign -- so an unknown never reads as a match.
    """
    left = operator_prefix(first)
    return left is not None and left == operator_prefix(second)
