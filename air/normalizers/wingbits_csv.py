"""Read a recorded Wingbits ADS-B CSV into ``AdsbObservation`` records.

Shared enabling work: this lives in ``air/normalizers/`` rather than inside a
detector so all three detector teams can use it.

The CSV uses short field codes (``h``, ``la``, ``lo``, ``ab`` ...). This module
is the single place that knows what those codes mean; everything downstream
sees the normalized ``AdsbObservation`` and never touches a raw column name.

Two decisions worth knowing about:

- **Barometric altitude only.** The file carries both barometric (``ab``) and
  geometric (``ag``) altitude. Mixing the two across a pair of aircraft
  invents vertical separation that does not exist, so we take ``ab``
  everywhere and record the choice in the detector's limitations.
- **Blank means blank.** pandas reads an empty cell as ``NaN``, which is a
  float and therefore passes any ``is not None`` check downstream. Every
  optional field is converted back to ``None`` so the abstain rules in the
  detector actually fire.

Usage::

    from air.normalizers.wingbits_csv import load_wingbits_csv

    obs = load_wingbits_csv("data/lynchburg_adsb.csv")
    window = load_wingbits_csv(path, start=t0, end=t1)
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from air.models.observation import AdsbObservation

#: Wingbits/readsb short column -> AdsbObservation field.
COLUMN_MAP: dict[str, str] = {
    "h": "icao24",
    "timestamp": "observed_at",
    "la": "latitude",
    "lo": "longitude",
    "ab": "altitude_ft",       # barometric, NOT ag (geometric)
    "gs": "ground_speed_kt",
    "tr": "track_deg",
    "br": "vertical_rate_fpm",
    "n": "nic",
    "np": "nacp",
    "f": "callsign",
}

#: Rows missing any of these cannot be used at all.
REQUIRED = ("h", "timestamp", "la", "lo")

_INT_FIELDS = ("nic", "nacp")


def _clean(value: Any) -> Any:
    """NaN / NaT / blank string -> None. Everything else passes through."""
    if value is None or value is pd.NaT:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def load_wingbits_csv(
    path: str | Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    usecols: Iterable[str] | None = None,
) -> list[AdsbObservation]:
    """Load a Wingbits CSV into ``AdsbObservation`` objects.

    Args:
        path: the CSV file.
        start: keep only reports at or after this time (tz-aware UTC).
        end: keep only reports at or before this time (tz-aware UTC).
        bbox: ``(min_lat, min_lon, max_lat, max_lon)`` bounding box filter.
        usecols: override which raw columns are read (mainly for tests).

    Returns:
        Observations in time order. Rows missing an id, timestamp or position
        are skipped rather than guessed at.
    """
    columns = list(usecols) if usecols is not None else list(COLUMN_MAP)
    frame = pd.read_csv(path, usecols=columns, low_memory=False)

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce", utc=True, format="mixed")
    frame = frame.dropna(subset=list(REQUIRED))

    if start is not None:
        frame = frame[frame["timestamp"] >= pd.Timestamp(start)]
    if end is not None:
        frame = frame[frame["timestamp"] <= pd.Timestamp(end)]
    if bbox is not None:
        min_lat, min_lon, max_lat, max_lon = bbox
        frame = frame[
            frame["la"].between(min_lat, max_lat) & frame["lo"].between(min_lon, max_lon)
        ]

    frame = frame.sort_values("timestamp")

    out: list[AdsbObservation] = []
    for row in frame.to_dict("records"):
        fields = {field: _clean(row.get(column)) for column, field in COLUMN_MAP.items()}
        for name in _INT_FIELDS:
            if fields.get(name) is not None:
                fields[name] = int(fields[name])
        observed_at = fields["observed_at"]
        fields["observed_at"] = observed_at.to_pydatetime() if hasattr(observed_at, "to_pydatetime") else observed_at
        out.append(AdsbObservation(**fields))
    return out


__all__ = ["COLUMN_MAP", "REQUIRED", "load_wingbits_csv"]
