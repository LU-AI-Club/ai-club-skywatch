"""Recorded KLYH-area examples of constant-motion prediction error."""

from dataclasses import replace
from datetime import datetime

import pytest

from air.detectors.proximity.config import load_config
from air.detectors.proximity.features import pair_geometry
from air.detectors.proximity.geometry import haversine_nm
from air.detectors.proximity.rules import flag_pair
from air.detectors.proximity.tracks import align_tracks
from contracts import SeverityLevel
from tests.conftest import load_observations


def _pair_at(fixture: str, time: str):
    snapshots = align_tracks(load_observations(fixture), load_config())
    pair = snapshots[datetime.fromisoformat(f"2026-09-01T{time}+00:00")]
    assert len(pair) == 2
    return sorted(pair, key=lambda obs: obs.icao24)


def test_klyh_turn_makes_predicted_horizontal_gap_one_nm_too_small():
    start = _pair_at("proximity_klyh_turn_real.json", "00:11:19")
    later = _pair_at("proximity_klyh_turn_real.json", "00:12:24")
    geometry = pair_geometry(*start)
    assert geometry is not None
    assert flag_pair(geometry, load_config()) is None  # 5,000 ft production floor
    assert flag_pair(geometry, replace(load_config(), min_altitude_ft=0)) is SeverityLevel.LOW
    assert geometry.t_cpa_s == pytest.approx(65, abs=1)

    actual_nm = haversine_nm(
        later[0].latitude, later[0].longitude,
        later[1].latitude, later[1].longitude,
    )
    assert geometry.predicted_horizontal_nm == pytest.approx(1.75, abs=0.02)
    assert actual_nm == pytest.approx(2.76, abs=0.02)
    assert actual_nm - geometry.predicted_horizontal_nm > 0.9
    assert abs(later[0].track_deg - start[0].track_deg) > 30
    assert abs(later[1].track_deg - start[1].track_deg) > 30


def test_klyh_vertical_rate_projection_misses_level_gap():
    start = _pair_at("proximity_klyh_vertical_real.json", "00:23:06")
    later = _pair_at("proximity_klyh_vertical_real.json", "00:24:38")
    geometry = pair_geometry(*start)
    assert geometry is not None
    assert flag_pair(geometry, load_config()) is None  # floor and INFO removal
    assert geometry.t_cpa_s == pytest.approx(92, abs=1)
    assert geometry.predicted_vertical_ft < 20

    actual_vertical_ft = abs(later[0].altitude_ft - later[1].altitude_ft)
    assert actual_vertical_ft == pytest.approx(1029, abs=5)
    assert actual_vertical_ft > 900  # outside the current INFO vertical gate
