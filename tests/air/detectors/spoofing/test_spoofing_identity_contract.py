"""The identity rules must accept AdsbObservation, not just dicts.

They were written against the raw feed's field names (`lat`, `lon`,
`timestamp`) while the pipeline passes `AdsbObservation`, whose contract
names are `latitude`, `longitude` and `observed_at`. These tests pin both
shapes so neither side can drift again.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.detector import SpoofingDetector
from air.detectors.spoofing.identity import (
    flag_coexistence,
    flag_identity_drift,
    flag_pingpong,
    flag_reappearance,
)
from air.models.observation import AdsbObservation

CFG = SpoofingConfig()
T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def obs(seconds: float, lat: float, lon: float, **kwargs) -> AdsbObservation:
    return AdsbObservation(
        icao24="a1b2c3",
        observed_at=T0 + timedelta(seconds=seconds),
        latitude=lat,
        longitude=lon,
        **kwargs,
    )


# --- the contract the pipeline actually passes -------------------------------
def test_coexistence_accepts_observations():
    """Two places at once, 300 km apart within 5 s."""
    pair = [obs(0, 37.0, -79.0), obs(5, 37.0, -75.5)]
    assert flag_coexistence(pair, CFG) is not None


def test_coexistence_is_quiet_on_one_aircraft_flying_normally():
    track = [obs(i * 5, 37.0 + i * 0.01, -79.0) for i in range(10)]
    assert flag_coexistence(track, CFG) is None


def test_reappearance_accepts_observations():
    """Gone 45 s, back 200 km away."""
    before, after = obs(0, 37.0, -79.0), obs(45, 37.0, -76.7)
    assert flag_reappearance(before, after, CFG) is not None


def test_reappearance_is_quiet_when_the_aircraft_could_have_got_there():
    before, after = obs(0, 37.0, -79.0), obs(120, 37.2, -79.0)
    assert flag_reappearance(before, after, CFG) is None


def test_pingpong_accepts_observations(observations_from):
    track = observations_from("spoofing/pos_impersonation.json")
    assert flag_pingpong(track, CFG) is not None


def test_identity_drift_accepts_observations():
    track = [
        obs(0, 37.0, -79.0, callsign="SKY101"),
        obs(5, 37.0, -79.0, callsign="SKY101"),
        obs(10, 37.0, -79.0, callsign="DAL900"),
    ]
    assert flag_identity_drift(track) is not None


def test_identity_drift_is_quiet_on_one_callsign():
    track = [obs(i * 5, 37.0, -79.0, callsign="SKY101") for i in range(5)]
    assert flag_identity_drift(track) is None


def test_the_old_dict_shape_still_works():
    """58 existing tests feed dicts; both shapes have to keep working."""
    pair = [
        {"icao24": "a1b2c3", "timestamp": 0, "lat": 37.0, "lon": -79.0},
        {"icao24": "a1b2c3", "timestamp": 5, "lat": 37.0, "lon": -75.5},
    ]
    assert flag_coexistence(pair) is not None


# --- wired into the pipeline -------------------------------------------------
def test_impersonation_is_caught_end_to_end(observations_from):
    obs_list = observations_from("spoofing/pos_impersonation.json")
    gates = {d.metadata["gate"] for d in SpoofingDetector().detect_observations(obs_list)}
    assert "coexistence_v1" in gates
    assert "pingpong_v1" in gates


def test_two_aircraft_flying_close_together_are_not_an_identity_finding(
    observations_from,
):
    """Different ids, so proximity alone must never read as impersonation."""
    obs_list = observations_from("spoofing/neg_close_formation.json")
    assert SpoofingDetector().detect_observations(obs_list) == []


def test_a_non_icao_address_does_not_crash_the_run():
    """readsb prefixes TIS-B and anonymised targets with "~".

    Those are not hex, so the registry lookup rejects them. The detector must
    abstain on such a track rather than take the whole replay down -- this
    crashed a full-file run before it was guarded.
    """
    from air.detectors.spoofing.reference import load_faa_registry, load_icao_blocks

    ref = "air/fixtures/spoofing"
    detector = SpoofingDetector(
        registry=load_faa_registry(f"{ref}/faa_registry_sample.csv"),
        icao_blocks=load_icao_blocks(f"{ref}/icao_blocks_sample.csv"),
    )
    track = [
        AdsbObservation(
            icao24="~aaae4b",
            observed_at=T0 + timedelta(seconds=i * 5),
            latitude=37.0 + i * 0.01,
            longitude=-79.0,
            ground_speed_kt=450.0,
        )
        for i in range(5)
    ]
    assert detector.detect_observations(track) == []
