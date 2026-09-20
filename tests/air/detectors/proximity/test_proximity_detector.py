"""End to end on the synthetic fixtures. OWNER: Paul (detect_observations).

These only go green once every lane's function is in. That is the MVP.
Run just these:  pytest tests/air/detectors/proximity/test_proximity_detector.py -q -rxX
"""

from __future__ import annotations

import json

import pytest

from air.detectors.proximity import ProximityDetector
from contracts import Detection, SeverityLevel
from tests.air.detectors.proximity._todo import todo
from tests.conftest import FIXTURES_DIR, load_observations

FIXTURES = [
    "proximity_head_on.json",
    "proximity_diverging.json",
    "proximity_stacked.json",
    "proximity_crossing_low.json",
    "proximity_ground.json",
]


def _expect(name):
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))[0]["_expect"]


@todo("Paul")
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_produces_expected_detections(fixture):
    expect = _expect(fixture)
    detections = ProximityDetector().detect_observations(load_observations(fixture))
    assert len(detections) == expect["detections"], fixture
    if expect["detections"]:
        assert detections[0].severity is SeverityLevel(expect["severity"])


@todo("Paul")
def test_one_encounter_is_one_detection_not_one_per_second():
    detections = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))
    assert len(detections) == 1


@todo("Paul")
def test_detection_is_the_real_contract_with_two_entities():
    det = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))[0]
    assert isinstance(det, Detection)
    assert sorted(e.entity_id for e in det.entities_involved) == ["aircraft:aaa001", "aircraft:bbb002"]
    d = det.to_dict()  # must serialise cleanly for TCE/CAATS
    assert d["detector_id"] == "skywatch.proximity"
    assert d["metadata"]["feature_schema_version"] == "air-features-v1"
    assert d["metadata"]["baseline_or_model_version"]
    assert d["provenance"]["processing_chain"][0]["parameters"]["max_tcpa_s"] == 120.0


@todo("Paul")
def test_explanation_facts_are_observations_not_conclusions():
    det = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))[0]
    facts = " ".join(det.metadata["explanation_facts"]).lower()
    for banned in ("dangerous", "violation", "unsafe", "threat", "intent"):
        assert banned not in facts
    assert "closest approach" in facts
    assert det.metadata["limitations"]


@todo("Paul")
def test_head_on_predicts_the_planted_geometry():
    det = ProximityDetector().detect_observations(load_observations("proximity_head_on.json"))[0]
    ev = det.evidence[0].metadata
    assert ev["predicted_horizontal_nm"] == pytest.approx(0.2, abs=0.02)
    assert ev["predicted_vertical_ft"] == pytest.approx(200.0, abs=5.0)
    assert 30 < ev["t_cpa_s"] <= 60
