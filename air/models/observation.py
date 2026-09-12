"""Normalized ADS-B observation — the air-domain input contract.

This is the SkyWatch equivalent of a normalized maritime AIS position. The
normalizer lane (shared enabling work) produces ``AdsbObservation`` records
from raw ADS-B (e.g. OpenSky state vectors); every detector consumes them.

Units are fixed HERE and never change downstream — that is the whole point of
a contract. If you change a unit, you change it once, here, and every lane
sees the same change.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


def _parse_dt(value: Any) -> datetime:
    """Accept a datetime or ISO-8601 string; return tz-aware UTC."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError("observed_at must be a datetime or ISO-8601 string")
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class AdsbObservation:
    """One normalized ADS-B position report for a single aircraft.

    Fields mirror the SkyWatch syllabus "ADS-B Normalizer" backlog item.
    Optional fields are ``None`` when the receiver did not report them — that
    is normal, and the false-positive lane cares about it.
    """

    icao24: str                       # 24-bit ICAO address, lowercase hex, e.g. "a1b2c3"
    observed_at: datetime             # UTC, timezone-aware
    latitude: float                   # WGS84 degrees
    longitude: float                  # WGS84 degrees
    altitude_ft: float | None = None  # feet (barometric or geometric)
    ground_speed_kt: float | None = None   # knots
    track_deg: float | None = None    # course over ground, 0-360
    vertical_rate_fpm: float | None = None  # feet per minute, + = climbing
    nic: int | None = None            # Navigation Integrity Category, 0-11
    nacp: int | None = None           # Navigation Accuracy Category - Position, 0-11
    squawk: str | None = None         # transponder code, e.g. "7700"
    callsign: str | None = None
    receiver_id: str | None = None    # which sensor heard it (receiver-health FP work)

    def __post_init__(self) -> None:
        if not isinstance(self.icao24, str) or not self.icao24.strip():
            raise ValueError("icao24 must be a non-blank string")
        object.__setattr__(self, "icao24", self.icao24.strip().lower())
        object.__setattr__(self, "observed_at", _parse_dt(self.observed_at))
        if not -90.0 <= float(self.latitude) <= 90.0:
            raise ValueError("latitude must be between -90 and 90")
        if not -180.0 <= float(self.longitude) <= 180.0:
            raise ValueError("longitude must be between -180 and 180")

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "AdsbObservation":
        """Build from a plain dict (e.g. one row of a fixture JSON file).

        Only known fields are read, so a fixture may carry extra annotation
        keys (like ``_label``) without breaking construction.
        """
        known = {f for f in cls.__slots__}  # type: ignore[attr-defined]
        return cls(**{k: v for k, v in payload.items() if k in known})


__all__ = ["AdsbObservation"]
