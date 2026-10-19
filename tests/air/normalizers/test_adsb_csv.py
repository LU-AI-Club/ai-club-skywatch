"""Tests for the readsb/tar1090 CSV -> AdsbObservation normalizer.

Fixture-based, no services (the repo's Definition of Done). The fixture
``fixtures/sample_rows.csv`` carries only the columns the normalizer reads,
each row chosen to exercise one rule:

    row 1  normal airborne         -> full mapping, units preserved
    row 2  on-ground (alt 25, gs 0)-> still emitted
    row 3  missing lat/lon         -> skipped
    row 4  all optionals empty     -> emitted, optionals None
    row 5  emergency squawk 7700   -> squawk kept as string
    row 6  br empty, gr present    -> vertical rate falls back to gr
    row 7  blank icao24            -> skipped
    row 8  callsign with spaces    -> stripped
"""

from __future__ import annotations

import csv
from datetime import timezone
from pathlib import Path

from air.normalizers.adsb_csv import (
    NormalizationStats,
    iter_observations,
    normalize_row,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_rows.csv"


def _rows() -> list[dict]:
    with open(FIXTURE, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_normal_row_maps_every_field_in_contract_units() -> None:
    obs = normalize_row(_rows()[0])
    assert obs is not None
    assert obs.icao24 == "ace81d"
    assert obs.latitude == 34.945816
    assert obs.longitude == -80.945136
    assert obs.altitude_ft == 4850.0
    assert obs.ground_speed_kt == 186.7
    assert obs.track_deg == 4.92
    assert obs.vertical_rate_fpm == 0.0  # from `br`
    assert obs.nic == 8
    assert obs.nacp == 9
    assert obs.squawk == "2575"
    assert obs.callsign == "AAL1715"
    # observed_at is parsed to tz-aware UTC by AdsbObservation
    assert obs.observed_at.tzinfo is not None
    assert obs.observed_at.astimezone(timezone.utc).year == 2026


def test_on_ground_row_is_emitted() -> None:
    obs = normalize_row(_rows()[1])
    assert obs is not None
    assert obs.altitude_ft == 25.0
    assert obs.ground_speed_kt == 0.0


def test_row_missing_position_is_skipped() -> None:
    assert normalize_row(_rows()[2]) is None


def test_empty_optionals_become_none_but_row_survives() -> None:
    obs = normalize_row(_rows()[3])
    assert obs is not None  # valid identity + position
    assert obs.latitude == 38.0
    assert obs.altitude_ft is None
    assert obs.ground_speed_kt is None
    assert obs.track_deg is None
    assert obs.vertical_rate_fpm is None
    assert obs.nic is None
    assert obs.nacp is None
    assert obs.squawk is None
    assert obs.callsign is None


def test_emergency_squawk_kept_as_string() -> None:
    obs = normalize_row(_rows()[4])
    assert obs is not None
    assert obs.squawk == "7700"


def test_vertical_rate_falls_back_to_geom_rate() -> None:
    obs = normalize_row(_rows()[5])
    assert obs is not None
    assert obs.vertical_rate_fpm == -512.0  # `br` empty -> `gr`


def test_blank_icao24_is_skipped() -> None:
    assert normalize_row(_rows()[6]) is None


def test_callsign_is_stripped() -> None:
    obs = normalize_row(_rows()[7])
    assert obs is not None
    assert obs.callsign == "PDT6098"


def test_receiver_id_override_is_stamped() -> None:
    obs = normalize_row(_rows()[0], receiver_id="lynchburg")
    assert obs is not None
    assert obs.receiver_id == "lynchburg"


def test_iter_observations_streams_and_counts() -> None:
    stats = NormalizationStats()
    obs = list(iter_observations(FIXTURE, stats=stats))
    # 8 rows in, 2 skipped (missing position, blank icao24) -> 6 out
    assert stats.total_rows == 8
    assert stats.skipped == 2
    assert stats.normalized == 6
    assert len(obs) == 6
    # order preserved; first emitted is the normal row
    assert obs[0].icao24 == "ace81d"


# --- ag / og / c / source_row_id (added for detectors that need them) --------
def _raw(**overrides: str) -> dict:
    """One inline readsb row with the extra columns the fixture file lacks."""
    row = {
        "h": "ace81d",
        "timestamp": "2026-09-01 00:00:00+00:00",
        "la": "37.3",
        "lo": "-79.2",
        "ab": "4850",
        "ag": "5200",
        "og": "False",
        "c": "A3",
    }
    row.update(overrides)
    return row


def test_geometric_altitude_and_emitter_category_are_mapped() -> None:
    obs = normalize_row(_raw())
    assert obs is not None
    assert obs.altitude_ft == 4850.0  # barometric stays in altitude_ft
    assert obs.alt_geom_ft == 5200.0
    assert obs.emitter_category == "A3"


def test_geometric_altitude_survives_blank_baro() -> None:
    obs = normalize_row(_raw(ab=""))
    assert obs is not None
    assert obs.altitude_ft is None
    assert obs.alt_geom_ft == 5200.0


def test_on_ground_parses_readsb_capitalized_strings() -> None:
    on = normalize_row(_raw(og="True"))
    off = normalize_row(_raw(og="False"))
    assert on is not None and on.on_ground is True
    assert off is not None and off.on_ground is False
    lower = normalize_row(_raw(og="true"))
    assert lower is not None and lower.on_ground is True


def test_on_ground_blank_or_junk_is_unknown_not_airborne() -> None:
    for value in ("", "maybe"):
        obs = normalize_row(_raw(og=value))
        assert obs is not None
        assert obs.on_ground is None


def test_rows_without_the_new_columns_still_normalize() -> None:
    """The fixture file has no ag/og/c columns: the new fields just stay None."""
    obs = normalize_row(_rows()[0])
    assert obs is not None
    assert obs.alt_geom_ft is None
    assert obs.on_ground is None
    assert obs.emitter_category is None


def test_iter_observations_stamps_source_row_ids() -> None:
    observations = list(iter_observations(FIXTURE))
    assert observations[0].source_row_id == f"{FIXTURE}:1"
    # Row 3 (missing position) is skipped, so the third observation is row 4:
    # ids track the file's rows, not the output position.
    assert observations[2].source_row_id == f"{FIXTURE}:4"


def test_normalize_row_passes_source_row_id_through() -> None:
    obs = normalize_row(_raw(), source_row_id="live:abc")
    assert obs is not None and obs.source_row_id == "live:abc"
