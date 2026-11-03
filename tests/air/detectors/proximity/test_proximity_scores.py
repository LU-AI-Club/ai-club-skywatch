"""The three score fields, which used to be the same number three times.

- ``anomaly_score``        how far outside normal this encounter is
- ``raw_model_confidence`` our certainty from the geometry alone
- ``confidence``           that, discounted by how well the aircraft know where
                           they are (NACp)

They answer different questions and must not track each other.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from air.detectors.proximity import (
    PairGeometry,
    anomaly_score_for,
    confidence_for,
    load_config,
    position_quality,
    raw_model_confidence_for,
)
from air.models.observation import AdsbObservation

CFG = load_config()
T0 = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)


def _geom(pred_h=0.2, pred_v=200.0, t_cpa=60.0, nacp_a=10, nacp_b=10):
    a = AdsbObservation(icao24="aaa001", observed_at=T0, latitude=37.4, longitude=-79.1,
                        altitude_ft=35000.0, ground_speed_kt=450.0, track_deg=90.0, nacp=nacp_a)
    b = AdsbObservation(icao24="bbb002", observed_at=T0, latitude=37.4, longitude=-79.0,
                        altitude_ft=35200.0, ground_speed_kt=450.0, track_deg=270.0, nacp=nacp_b)
    return PairGeometry(
        icao_a="aaa001", icao_b="bbb002", at=T0, horizontal_now_nm=5.0,
        vertical_now_ft=200.0, closure_rate_kt=900.0, t_cpa_s=t_cpa,
        predicted_horizontal_nm=pred_h, predicted_vertical_ft=pred_v, obs_a=a, obs_b=b,
    )


# --- anomaly_score: how far outside normal -------------------------------------
def test_collision_is_maximally_anomalous():
    assert anomaly_score_for(_geom(pred_h=0.0, pred_v=0.0), CFG) == 1.0


def test_pair_on_the_loosest_boundary_is_not_anomalous():
    loosest_h = max(t.max_horizontal_nm for t in CFG.tiers)
    assert anomaly_score_for(_geom(pred_h=loosest_h, pred_v=0.0), CFG) == 0.0


def test_anomaly_rises_as_the_pair_gets_closer():
    far = anomaly_score_for(_geom(pred_h=2.9, pred_v=100), CFG)
    near = anomaly_score_for(_geom(pred_h=0.1, pred_v=100), CFG)
    assert 0.0 <= far < near <= 1.0


def test_the_binding_dimension_decides():
    """Both limits must hold to fire, so whichever is proportionally closer to
    its limit is the one that caps how anomalous the pair is."""
    loosest_v = max(t.max_vertical_ft for t in CFG.tiers)
    # Touching horizontally, but vertically right on the boundary.
    assert anomaly_score_for(_geom(pred_h=0.0, pred_v=loosest_v), CFG) == 0.0


def test_anomaly_ignores_lookahead():
    """How unusual an encounter is does not depend on how far ahead we looked."""
    assert anomaly_score_for(_geom(t_cpa=5), CFG) == anomaly_score_for(_geom(t_cpa=115), CFG)


# --- raw_model_confidence: geometry only ----------------------------------------
def test_raw_confidence_is_highest_right_now():
    assert raw_model_confidence_for(_geom(t_cpa=0.0), CFG) == 1.0


def test_raw_confidence_halves_at_the_prediction_horizon():
    assert raw_model_confidence_for(_geom(t_cpa=CFG.max_tcpa_s), CFG) == 0.5


def test_raw_confidence_ignores_how_close_they_get():
    """Certainty about the geometry is not severity."""
    assert raw_model_confidence_for(_geom(pred_h=0.0), CFG) == raw_model_confidence_for(_geom(pred_h=2.9), CFG)


# --- position_quality: what the aircraft say about their own GPS ------------------
def test_good_gps_is_not_discounted_much():
    assert position_quality(_geom(nacp_a=10, nacp_b=10), CFG) > 0.98


def test_poor_gps_is_discounted_hard():
    # NACp 5 means the position may be half a mile out, which is our entire
    # HIGH threshold.
    assert position_quality(_geom(nacp_a=10, nacp_b=5), CFG) <= 0.3


def test_the_worse_aircraft_decides():
    both_good = position_quality(_geom(nacp_a=10, nacp_b=10), CFG)
    one_bad = position_quality(_geom(nacp_a=10, nacp_b=6), CFG)
    assert one_bad < both_good


def test_unreported_nacp_is_treated_as_mediocre():
    unknown = position_quality(_geom(nacp_a=None, nacp_b=10), CFG)
    assert 0.3 <= unknown < position_quality(_geom(nacp_a=10, nacp_b=10), CFG)


def test_quality_never_reaches_zero():
    assert position_quality(_geom(nacp_a=1, nacp_b=1), CFG) >= 0.3


# --- confidence: the two combined --------------------------------------------------
def test_confidence_is_raw_discounted_by_position_quality():
    g = _geom(nacp_a=10, nacp_b=6)
    assert confidence_for(g, CFG) == pytest.approx(
        raw_model_confidence_for(g, CFG) * position_quality(g, CFG), abs=0.002)


def test_poor_gps_lowers_confidence_but_not_raw():
    good, bad = _geom(nacp_a=10, nacp_b=10), _geom(nacp_a=10, nacp_b=5)
    assert raw_model_confidence_for(good, CFG) == raw_model_confidence_for(bad, CFG)
    assert confidence_for(bad, CFG) < confidence_for(good, CFG)


# --- the three are genuinely different ----------------------------------------------
def test_the_three_scores_are_not_the_same_number():
    g = _geom(pred_h=0.2, pred_v=200.0, t_cpa=60.0, nacp_a=10, nacp_b=6)
    scores = {anomaly_score_for(g, CFG), raw_model_confidence_for(g, CFG), confidence_for(g, CFG)}
    assert len(scores) == 3, f"expected three distinct values, got {scores}"


def test_emitted_detection_carries_all_three():
    from tests.conftest import load_observations
    from air.detectors.proximity import ProximityDetector

    det = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))[0]
    meta = det.metadata
    assert 0.0 <= meta["anomaly_score"] <= 1.0
    assert 0.0 <= meta["raw_model_confidence"] <= 1.0
    assert 0.0 <= meta["position_quality"] <= 1.0
    assert det.confidence == pytest.approx(
        meta["raw_model_confidence"] * meta["position_quality"], abs=0.002)
