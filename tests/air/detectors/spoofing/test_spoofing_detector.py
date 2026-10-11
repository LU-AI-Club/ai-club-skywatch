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


def test_runs_on_a_spoofed_fixture_without_raising(observations_from):
    """No rules are merged yet, so this is quiet today and should not be later."""
    obs = observations_from("spoofing/pos_teleport.json")
    assert SpoofingDetector().detect_observations(obs) == []


def test_detect_reads_observations_from_the_context(observations_from):
    """The platform entry point pulls from auxiliary_data, as the reference does."""
    obs = observations_from("spoofing/pos_teleport.json")
    context = DetectionContext(auxiliary_data={"observations": obs})
    assert SpoofingDetector().detect(context) == []


def test_detect_survives_an_empty_context():
    assert SpoofingDetector().detect(DetectionContext()) == []
