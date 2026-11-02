"""Tests for the Lynchburg CSV normalizer."""

from __future__ import annotations

import csv
from datetime import timezone

import pytest

from air.normalizers.lynchburg_csv import (
    is_direct_adsb,
    load_csv,
    rc_to_nic,
    row_to_observation,
)


def _row(**overrides):
    """A believable direct-reception row; override what a test cares about."""
    row = {
        "t": "adsb_icao",
        "h": "a1b2c3",
        "timestamp": "2026-09-01 00:25:40.236000+00:00",
        "la": "37.4138",
        "lo": "-79.1422",
        "ag": "35000",
        "ab": "34200",
        "gs": "450.0",
        "tr": "45.0",
        "br": "0.0",
        "rc": "186.0",
        "np": "9",
        "sq": "1200",
        "f": "SKY101",
    }
    row.update(overrides)
    return row


# --- rc_to_nic ---------------------------------------------------------------
@pytest.mark.parametrize(
    "rc_m, expected",
    [(7.5, 11), (25.0, 10), (75.0, 9), (186.0, 8), (371.0, 7), (1852.0, 5)],
)
def test_band_boundaries_map_to_their_nic(rc_m, expected):
    """Each bound is the worst radius still inside its band."""
    assert rc_to_nic(rc_m) == expected


def test_value_inside_a_band_takes_that_band():
    # 100 m is worse than 75 (NIC 9) but still within 186 (NIC 8).
    assert rc_to_nic(100.0) == 8


def test_unknown_radius_abstains():
    """0 means unknown in this feed, and must not read as NIC 0."""
    assert rc_to_nic(None) is None
    assert rc_to_nic(0.0) is None
    assert rc_to_nic(-5.0) is None


def test_radius_past_the_table_is_nic_zero():
    assert rc_to_nic(40000.0) == 0


# --- is_direct_adsb ----------------------------------------------------------
def test_direct_reception_is_kept():
    assert is_direct_adsb(_row(t="adsb_icao")) is True


@pytest.mark.parametrize("source", ["adsr_icao", "tisb_other", "", "ADSB_OTHER"])
def test_relayed_and_unknown_sources_are_dropped(source):
    assert is_direct_adsb(_row(t=source)) is False


def test_missing_source_column_is_dropped():
    row = _row()
    del row["t"]
    assert is_direct_adsb(row) is False


# --- row_to_observation ------------------------------------------------------
def test_a_good_row_maps_every_column():
    obs = row_to_observation(_row())
    assert obs is not None
    assert obs.icao24 == "a1b2c3"
    assert obs.latitude == 37.4138
    assert obs.longitude == -79.1422
    assert obs.altitude_ft == 35000.0      # ag, the GPS altitude
    assert obs.ground_speed_kt == 450.0
    assert obs.track_deg == 45.0
    assert obs.vertical_rate_fpm == 0.0
    assert obs.nic == 8                     # rc 186 -> NIC 8
    assert obs.nacp == 9
    assert obs.callsign == "SKY101"
    assert obs.observed_at.tzinfo is not None
    assert obs.observed_at.astimezone(timezone.utc).hour == 0


def test_geometric_altitude_is_used_not_barometric():
    """ag and ab differ by hundreds of feet; mixing them invents climbs."""
    obs = row_to_observation(_row(ag="35000", ab="34200"))
    assert obs is not None
    assert obs.altitude_ft == 35000.0


def test_relayed_rows_are_rejected():
    assert row_to_observation(_row(t="tisb_other")) is None


@pytest.mark.parametrize("field", ["h", "timestamp", "la", "lo"])
def test_rows_missing_an_essential_field_are_rejected(field):
    assert row_to_observation(_row(**{field: ""})) is None


def test_blank_optional_fields_become_none_not_zero():
    """Not reported is not the same as zero."""
    obs = row_to_observation(_row(ag="", gs="", br="", rc="", sq=""))
    assert obs is not None
    assert obs.altitude_ft is None
    assert obs.ground_speed_kt is None
    assert obs.vertical_rate_fpm is None
    assert obs.nic is None
    assert obs.squawk is None


def test_out_of_range_position_is_rejected_not_raised():
    assert row_to_observation(_row(la="999")) is None


def test_unparseable_timestamp_is_rejected_not_raised():
    assert row_to_observation(_row(timestamp="not a date")) is None


# --- load_csv ----------------------------------------------------------------
def _write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def test_load_csv_keeps_good_rows_and_skips_the_rest(tmp_path):
    path = tmp_path / "sample.csv"
    _write_csv(
        path,
        [
            _row(h="a1b2c3"),
            _row(h="d4e5f6", t="tisb_other"),   # relayed -> skipped
            _row(h="aa11bb", la=""),            # no position -> skipped
            _row(h="bb22cc"),
        ],
    )
    observations = load_csv(path)
    assert [o.icao24 for o in observations] == ["a1b2c3", "bb22cc"]


def test_load_csv_on_an_empty_file(tmp_path):
    path = tmp_path / "empty.csv"
    _write_csv(path, [_row()])
    path.write_text("t,h,timestamp,la,lo\n", encoding="utf-8")
    assert load_csv(path) == []
