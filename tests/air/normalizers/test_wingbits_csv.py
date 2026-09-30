"""Tests for the Wingbits CSV normalizer.

Run against air/fixtures/wingbits_sample.csv (50 rows), never the 70 MB file.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from air.models.observation import AdsbObservation
from air.normalizers.wingbits_csv import COLUMN_MAP, load_wingbits_csv

SAMPLE = Path(__file__).resolve().parents[3] / "air" / "fixtures" / "wingbits_sample.csv"


@pytest.fixture(scope="module")
def observations() -> list[AdsbObservation]:
    return load_wingbits_csv(SAMPLE)


def test_returns_adsb_observations(observations):
    assert observations
    assert all(isinstance(o, AdsbObservation) for o in observations)


def test_known_row_maps_correctly(observations):
    # First data row of the sample: AAL1715 south of Charlotte.
    obs = next(o for o in observations if o.icao24 == "ace81d")
    assert obs.callsign == "AAL1715"
    assert obs.latitude == pytest.approx(34.945816)
    assert obs.longitude == pytest.approx(-80.945136)
    assert obs.altitude_ft == pytest.approx(4850.0)     # ab, barometric
    assert obs.ground_speed_kt == pytest.approx(186.7)
    assert obs.track_deg == pytest.approx(4.92, abs=0.01)
    assert obs.nic == 8 and obs.nacp == 9


def test_uses_barometric_not_geometric_altitude(observations):
    # Row 0 has ab=4850 and ag=5200. Taking the wrong one invents 350 ft of
    # separation on every pair.
    obs = next(o for o in observations if o.icao24 == "ace81d")
    assert obs.altitude_ft == pytest.approx(4850.0)
    assert obs.altitude_ft != pytest.approx(5200.0)


def test_blank_cells_become_none_not_nan(observations):
    # The sample has rows with no barometric vertical rate. None means
    # "not reported"; NaN would sail through every `is not None` check.
    missing = [o for o in observations if o.vertical_rate_fpm is None]
    assert missing, "sample should contain at least one blank vertical rate"
    assert all(o.vertical_rate_fpm == o.vertical_rate_fpm for o in observations if o.vertical_rate_fpm is not None)


def test_timestamps_are_utc_aware_and_sorted(observations):
    assert all(o.observed_at.tzinfo is not None for o in observations)
    assert all(o.observed_at.utcoffset().total_seconds() == 0 for o in observations)
    times = [o.observed_at for o in observations]
    assert times == sorted(times)


def test_icao_is_lowercase_hex(observations):
    assert all(o.icao24 == o.icao24.lower() for o in observations)


def test_time_filter_narrows_the_result(observations):
    midpoint = observations[len(observations) // 2].observed_at
    later = load_wingbits_csv(SAMPLE, start=midpoint)
    assert 0 < len(later) < len(observations)
    assert all(o.observed_at >= midpoint for o in later)


def test_time_filter_with_no_matches_returns_empty():
    future = datetime(2030, 1, 1, tzinfo=timezone.utc)
    assert load_wingbits_csv(SAMPLE, start=future) == []


def test_bbox_filter_narrows_the_result(observations):
    # A box around Charlotte, well inside the sample's spread.
    boxed = load_wingbits_csv(SAMPLE, bbox=(34.5, -81.5, 35.5, -80.0))
    assert 0 < len(boxed) < len(observations)
    assert all(34.5 <= o.latitude <= 35.5 for o in boxed)


def test_rows_without_a_position_are_skipped(tmp_path):
    header = SAMPLE.read_text(encoding="utf-8").splitlines()[0]
    good = SAMPLE.read_text(encoding="utf-8").splitlines()[1]
    broken = good.split(",")
    columns = header.split(",")
    broken[columns.index("la")] = ""          # no latitude -> unusable
    path = tmp_path / "broken.csv"
    path.write_text("\n".join([header, good, ",".join(broken)]) + "\n", encoding="utf-8")
    assert len(load_wingbits_csv(path)) == 1


def test_column_map_covers_every_observation_field_we_populate():
    assert set(COLUMN_MAP.values()) <= {f for f in AdsbObservation.__slots__}
