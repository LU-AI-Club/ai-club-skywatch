"""Tests for run_on_fixtures.

No real spoofing detector exists yet (only air/detectors/spoofing/records.py
does), so this is tested against two hand-built fake detectors instead of a
real one. That's enough to check the wiring - every fixture loaded, labels
read correctly, detections attached - independent of anyone else's
unfinished lane.
"""

from __future__ import annotations

from pathlib import Path

from air.models.observation import AdsbObservation
from scripts.evaluate_spoofing import run_on_fixtures

FIXTURES_DIR = Path(__file__).resolve().parents[4] / "air" / "fixtures" / "spoofing"


class AlwaysFiresDetector:
    def detect_observations(self, observations: list[AdsbObservation]) -> list[str]:
        return ["fake detection"] if observations else []


class NeverFiresDetector:
    def detect_observations(self, observations: list[AdsbObservation]) -> list[str]:
        return []


def test_runs_every_fixture_file():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    json_files = list(FIXTURES_DIR.glob("*.json"))
    assert len(results) == len(json_files)


def test_skips_non_json_files():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    names = {r["fixture_name"] for r in results}
    assert "icao_blocks_sample.csv" not in names
    assert "faa_registry_sample.csv" not in names
    assert "README.md" not in names


def test_reads_expected_label_from_positive_fixture():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    by_name = {r["fixture_name"]: r for r in results}
    teleport = by_name["pos_teleport.json"]
    assert teleport["expected_positive"] is True
    assert teleport["expected_gate"] == "teleport_v1"


def test_reads_expected_label_from_negative_fixture():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    by_name = {r["fixture_name"]: r for r in results}
    tailwind = by_name["neg_tailwind_cruise.json"]
    assert tailwind["expected_positive"] is False
    assert tailwind["expected_gate"] == "teleport_v1"


def test_clean_track_has_no_gate_label():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    by_name = {r["fixture_name"]: r for r in results}
    clean = by_name["clean_track.json"]
    assert clean["expected_positive"] is False
    assert clean["expected_gate"] == "unlabeled"


def test_never_fires_detector_reports_no_detections():
    results = run_on_fixtures(NeverFiresDetector(), FIXTURES_DIR)
    assert all(r["fired"] is False for r in results)
    assert all(r["detections"] == [] for r in results)


def test_always_fires_detector_reports_detections():
    results = run_on_fixtures(AlwaysFiresDetector(), FIXTURES_DIR)
    assert all(r["fired"] is True for r in results)
    assert all(r["detections"] == ["fake detection"] for r in results)
