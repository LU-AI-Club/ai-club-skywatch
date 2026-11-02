"""Tests for the SpoofingDetector wiring.

These check the shape of the detector, not its judgement -- the rules are not
merged yet. What they prove is that the class satisfies the platform contract
and runs end to end over real fixture data without raising.

The clean-track test keeps earning its keep later: once the rules land, a
normal flight must still produce nothing.
"""

from __future__ import annotations

from contracts import DetectionContext, DetectorImplementationType

from air.detectors.spoofing.detector import SpoofingDetector


def test_metadata_matches_the_platform_contract():
    detector = SpoofingDetector()
    assert detector.detector_id == "skywatch.spoofing"
    assert detector.detector_version == "0.1.0"
    assert detector.domain == "air"
    assert detector.implementation_type is DetectorImplementationType.RULE_BASED


def test_required_data_declares_what_it_needs():
    required = SpoofingDetector().get_required_data()
    assert "adsb_position" in required.observation_types
    assert "adsb" in required.source_names
    assert "observations" in required.auxiliary_data_keys
    # Every check compares against earlier reports, so it needs history.
    assert required.lookback_hours == 1.0


def test_no_observations_produces_nothing():
    assert SpoofingDetector().detect_observations([]) == []


def test_runs_on_a_clean_fixture_without_raising(observations_from):
    """A normal flight must not raise, and must not be flagged."""
    obs = observations_from("spoofing/clean_track.json")
    assert len(obs) == 40
    assert SpoofingDetector().detect_observations(obs) == []


def test_a_teleport_is_caught_end_to_end(observations_from):
    """The whole pipeline, from observations to a platform Detection."""
    obs = observations_from("spoofing/pos_teleport.json")
    detections = SpoofingDetector().detect_observations(obs)
    assert detections
    assert "teleport_v1" in {d.metadata["gate"] for d in detections}


def test_detect_reads_observations_from_the_context(observations_from):
    """The platform entry point pulls from auxiliary_data, as the reference does."""
    obs = observations_from("spoofing/pos_teleport.json")
    context = DetectionContext(auxiliary_data={"observations": obs})
    assert SpoofingDetector().detect(context)


def test_every_positive_fixture_fires_its_gate(observations_from):
    expected = {
        "pos_teleport.json": "teleport_v1",
        "pos_impossible_turn.json": "turn_rate_v1",
        "pos_speed_contradiction.json": "speed_delta_v1",
        "pos_speed_lie_short_interval.json": "speed_delta_v1",
        "pos_vrate_contradiction.json": "vrate_delta_v1",
        "pos_integrity_collapse.json": "nic_floor_v1",
    }
    detector = SpoofingDetector()
    for fixture, gate in expected.items():
        detections = detector.detect_observations(observations_from(f"spoofing/{fixture}"))
        assert gate in {d.metadata["gate"] for d in detections}, fixture


def test_every_negative_fixture_stays_quiet(observations_from):
    """A rule that flags everything is useless; these prove it does not."""
    quiet = [
        "clean_track.json",
        "neg_tailwind_cruise.json",
        "neg_standard_turn.json",
        "neg_legal_descent.json",
        "neg_benign_gap.json",
        "neg_brief_nic_dip.json",
        "neg_ground_vehicle.json",
        "neg_sparse_track.json",
        "neg_short_interval_jitter.json",
    ]
    detector = SpoofingDetector()
    for fixture in quiet:
        detections = detector.detect_observations(observations_from(f"spoofing/{fixture}"))
        assert detections == [], fixture


def test_detect_survives_an_empty_context():
    assert SpoofingDetector().detect(DetectionContext()) == []
