"""Candidate pairs + cheap filters. OWNER: CalebG.

Run just these:  pytest tests/air/detectors/proximity/test_proximity_pairs.py -q -rxX
"""

from __future__ import annotations

from datetime import datetime, timezone

from air.detectors.proximity import load_config
from air.detectors.proximity.pairs import candidate_pairs, cell_of, is_airborne
from air.models.observation import AdsbObservation
from tests.air.detectors.proximity._todo import todo

T0 = datetime(2026, 9, 1, 0, 30, 0, tzinfo=timezone.utc)
CFG = load_config()


def _obs(icao, lat=37.4, lon=-79.1, alt=10000.0, gs=300.0, track=90.0):
    return AdsbObservation(
        icao24=icao, observed_at=T0, latitude=lat, longitude=lon,
        altitude_ft=alt, ground_speed_kt=gs, track_deg=track,
    )


def _ids(pairs):
    return [(a.icao24, b.icao24) for a, b in pairs]


# --- cell_of: done --------------------------------------------------------------
def test_cell_of_is_stable_within_a_cell():
    assert cell_of(_obs("a", 37.41, -79.14), 0.5) == cell_of(_obs("b", 37.49, -79.01), 0.5)
    assert cell_of(_obs("a", 37.41, -79.14), 0.5) != cell_of(_obs("b", 37.51, -79.14), 0.5)


# --- is_airborne ----------------------------------------------------------------
@todo("CalebG")
def test_cruising_aircraft_is_airborne():
    assert is_airborne(_obs("a", alt=35000.0, gs=450.0), CFG)


@todo("CalebG")
def test_taxiing_aircraft_is_not_airborne():
    assert not is_airborne(_obs("a", alt=940.0, gs=15.0), CFG)


@todo("CalebG")
def test_slow_but_high_is_airborne():
    # A helicopter hovering at 4,000 ft is slow, but it is flying.
    assert is_airborne(_obs("a", alt=4000.0, gs=10.0), CFG)


@todo("CalebG")
def test_low_but_fast_is_airborne():
    # Short final at 1,200 ft and 130 kt is flying.
    assert is_airborne(_obs("a", alt=1200.0, gs=130.0), CFG)


@todo("CalebG")
def test_missing_altitude_or_speed_abstains():
    assert not is_airborne(_obs("a", alt=None), CFG)
    assert not is_airborne(_obs("a", gs=None), CFG)


# --- candidate_pairs ------------------------------------------------------------
@todo("CalebG")
def test_two_nearby_airborne_aircraft_form_one_pair():
    pairs = candidate_pairs([_obs("bbb"), _obs("aaa", lon=-79.0)], CFG)
    assert _ids(pairs) == [("aaa", "bbb")]  # sorted, each pair once


@todo("CalebG")
def test_stacked_pair_is_dropped():
    pairs = candidate_pairs([_obs("aaa"), _obs("bbb", alt=10000.0 + CFG.max_vertical_prefilter_ft + 1)], CFG)
    assert pairs == []


@todo("CalebG")
def test_ground_pair_is_dropped():
    pairs = candidate_pairs([_obs("aaa", alt=940.0, gs=15.0), _obs("bbb", alt=940.0, gs=20.0)], CFG)
    assert pairs == []


@todo("CalebG")
def test_far_apart_aircraft_are_not_compared():
    # Same altitude, but three grid cells apart -> never even considered.
    pairs = candidate_pairs([_obs("aaa", lat=37.4), _obs("bbb", lat=37.4 + 3 * CFG.cell_size_deg)], CFG)
    assert pairs == []


@todo("CalebG")
def test_neighbouring_cells_are_compared():
    # Just across a cell boundary, including diagonally.
    a = _obs("aaa", lat=37.49, lon=-79.01)
    b = _obs("bbb", lat=37.51, lon=-78.99)
    assert _ids(candidate_pairs([a, b], CFG)) == [("aaa", "bbb")]


@todo("CalebG")
def test_missing_velocity_abstains():
    assert candidate_pairs([_obs("aaa", track=None), _obs("bbb")], CFG) == []


@todo("CalebG")
def test_same_icao_is_not_paired_with_itself():
    assert candidate_pairs([_obs("aaa"), _obs("aaa", lon=-79.0)], CFG) == []


@todo("CalebG")
def test_three_aircraft_give_three_pairs_each_once():
    pairs = candidate_pairs([_obs("ccc"), _obs("aaa", lon=-79.0), _obs("bbb", lon=-79.2)], CFG)
    assert _ids(pairs) == [("aaa", "bbb"), ("aaa", "ccc"), ("bbb", "ccc")]
