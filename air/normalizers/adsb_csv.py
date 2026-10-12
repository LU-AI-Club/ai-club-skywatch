"""Normalize raw readsb/tar1090 ADS-B CSV rows into ``AdsbObservation``.

This is **shared enabling infrastructure** (Tech-Lead owned), not detector
logic. It turns one row of a readsb-style CSV dump (the format of
``data/lynchburg_adsb.csv``) into the air-domain input contract,
``air.models.AdsbObservation``, so every detector consumes the same clean,
unit-fixed objects.

Design rules (match the rest of the repo):

* **Stdlib only** — ``csv`` + ``datetime``. No pandas, no network, no services.
* **Pure row -> object mapping.** Time-ordering, windowing and batching are the
  *runner's* job, deliberately kept out of here (the source file is ~99.9%
  time-sorted but not perfectly, so the runner sorts).
* **Abstain over guess.** A row we cannot trust (no position, blank identity,
  garbled coordinates) is *skipped*, not emitted as junk. A single bad optional
  field (e.g. an unparseable vertical rate) never discards an otherwise-good
  position — that one field just becomes ``None``.

The column-to-field mapping and the columns we intentionally ignore are
documented in ``COLUMN_MAP.md`` next to this file. The export is already in the
contract's units (feet / knots / fpm / degrees), so there is **no unit
conversion** here.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping

import csv

from air.models.observation import AdsbObservation

# --- Column names (documented map; see COLUMN_MAP.md) ------------------------
COL_ICAO24 = "h"            # 24-bit ICAO hex address
COL_TIMESTAMP = "timestamp"  # canonical position time ("...+00:00"); `ra` dupes it
COL_LAT = "la"
COL_LON = "lo"
COL_ALT_BARO = "ab"          # barometric altitude, feet
COL_GROUND_SPEED = "gs"      # knots
COL_TRACK = "tr"             # course over ground, degrees (`th` true-heading is empty here)
COL_BARO_RATE = "br"         # barometric vertical rate, fpm (primary)
COL_GEOM_RATE = "gr"         # geometric vertical rate, fpm (fallback for `br`)
COL_NIC = "n"                # Navigation Integrity Category
COL_NACP = "np"             # Navigation Accuracy Category - Position
COL_SQUAWK = "sq"            # 4-digit transponder code
COL_CALLSIGN = "f"           # flight id / callsign (padded with spaces in ADS-B)


# --- Small, forgiving field parsers ------------------------------------------
def _opt_float(value: Any) -> float | None:
    """Parse an optional float. Empty string or junk -> None (abstain)."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _opt_int(value: Any) -> int | None:
    """Parse an optional int. Accepts '8' or '8.0'. Empty/junk -> None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _opt_str(value: Any) -> str | None:
    """Strip a string field. Empty -> None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_row(
    row: Mapping[str, Any], *, receiver_id: str | None = None
) -> AdsbObservation | None:
    """Map one raw CSV row to an ``AdsbObservation``, or ``None`` to skip it.

    We skip (abstain) when the row has no usable identity or position, since a
    detector can do nothing with those. Every other field is optional and
    becomes ``None`` if absent or unparseable — we never throw away a good
    position because one secondary field was malformed.
    """
    icao24 = _opt_str(row.get(COL_ICAO24))
    if icao24 is None:
        return None  # no identity -> nothing a detector can attribute

    latitude = _opt_float(row.get(COL_LAT))
    longitude = _opt_float(row.get(COL_LON))
    if latitude is None or longitude is None:
        return None  # position is required by the contract -> skip

    # Vertical rate: prefer barometric (`br`), fall back to geometric (`gr`).
    vertical_rate = _opt_float(row.get(COL_BARO_RATE))
    if vertical_rate is None:
        vertical_rate = _opt_float(row.get(COL_GEOM_RATE))

    try:
        return AdsbObservation(
            icao24=icao24,
            observed_at=row.get(COL_TIMESTAMP),  # AdsbObservation parses to tz-aware UTC
            latitude=latitude,
            longitude=longitude,
            altitude_ft=_opt_float(row.get(COL_ALT_BARO)),
            ground_speed_kt=_opt_float(row.get(COL_GROUND_SPEED)),
            track_deg=_opt_float(row.get(COL_TRACK)),
            vertical_rate_fpm=vertical_rate,
            nic=_opt_int(row.get(COL_NIC)),
            nacp=_opt_int(row.get(COL_NACP)),
            squawk=_opt_str(row.get(COL_SQUAWK)),
            callsign=_opt_str(row.get(COL_CALLSIGN)),
            receiver_id=receiver_id,
        )
    except (ValueError, TypeError):
        # Bad timestamp, out-of-range coordinate, etc. Messy external data:
        # abstain on the row rather than crash the whole ingest.
        return None


@dataclass
class NormalizationStats:
    """Row counts for logging. Accurate once the generator is fully consumed."""

    total_rows: int = 0
    normalized: int = 0
    skipped: int = 0


def iter_observations(
    path: str | Path,
    *,
    receiver_id: str | None = None,
    stats: NormalizationStats | None = None,
) -> Iterator[AdsbObservation]:
    """Stream a readsb CSV file as ``AdsbObservation`` objects (file order).

    Unmappable rows are skipped silently. Pass a ``NormalizationStats`` to
    collect ``total_rows`` / ``normalized`` / ``skipped`` for a one-line summary
    (e.g. ``normalized 279207, skipped 5269``). Ordering/windowing is the
    runner's responsibility — this yields rows as they appear in the file.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if stats is not None:
                stats.total_rows += 1
            obs = normalize_row(row, receiver_id=receiver_id)
            if obs is None:
                if stats is not None:
                    stats.skipped += 1
                continue
            if stats is not None:
                stats.normalized += 1
            yield obs


__all__ = [
    "normalize_row",
    "iter_observations",
    "NormalizationStats",
]
