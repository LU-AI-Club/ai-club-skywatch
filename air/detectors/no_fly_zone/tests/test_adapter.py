"""Lead tests - adapter.py and build_detector().

Covers the bridge from the shared runner's ``AdsbObservation`` windows into
the NFZ pipeline: the field mapping and its fallbacks, firing and non-firing
cases through the real stages, the ``BaseDetector`` entry point, that
``scripts/replay_csv.py`` now finds the detector, and parity with the CLI path
on the fixture track.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from air.models.observation import AdsbObservation
from contracts import DetectionContext

from .. import build_detector
from ..adapter import NoFlyZoneDetector, observation_to_state
from ..emit import to_platform_detection
from ..ingest.adsb_loader import load_states
from ..ingest.airspace_loader import load_zones
from ..logic.detector import run
from ..types import ExitReason
from .conftest import AIRSPACE_FILE, TRACKS_FILE

pytest.importorskip("shapely")
pytest.importorskip("h3")

REPO_ROOT = Path(__file__).resolve().parents[4]
_TS = datetime(2026, 9, 22, 20, 15, tzinfo=UTC)


def make_obs(**overrides: Any) -> AdsbObservation:
    """An AdsbObservation inside fixture zone P-901, below its ceiling."""
    base: dict[str, Any] = {
        "icao24": "a1b2c3",
        "observed_at": _TS,
        "latitude": 37.425,
        "longitude": -79.215,
        "altitude_ft": 4850.0,
        "alt_geom_ft": 5200.0,
        "ground_speed_kt": 186.7,
        "track_deg": 4.9,
        "callsign": "TEST123",
        "squawk": "1200",
        "emitter_category": "A3",
        "nic": 8,
        "nacp": 9,
        "on_ground": False,
        "source_row_id": "test.csv:7",
    }
    base.update(overrides)
    return AdsbObservation(**base)


@pytest.fixture
def detector() -> NoFlyZoneDetector:
    return build_detector()


# ------------------------------------------------------------- field mapping

def test_observation_to_state_maps_every_field() -> None:
    state = observation_to_state(make_obs())
    assert state.icao24 == "a1b2c3"
    assert state.timestamp == _TS
    assert (state.lat, state.lon) == (37.425, -79.215)
    assert state.alt_baro_ft == 4850.0
    assert state.alt_geom_ft == 5200.0
    assert state.ground_speed_kt == 186.7
    assert state.track_deg == 4.9
    assert (state.callsign, state.squawk) == ("TEST123", "1200")
    assert state.emitter_category == "A3"
    assert (state.nic, state.nac_p) == (8, 9)
    assert state.on_ground is False
    assert state.source_row_id == "test.csv:7"


def test_unknown_on_ground_is_treated_as_airborne() -> None:
    assert observation_to_state(make_obs(on_ground=None)).on_ground is False
    assert observation_to_state(make_obs(on_ground=True)).on_ground is True


def test_missing_source_row_id_falls_back_to_icao_at_timestamp() -> None:
    state = observation_to_state(make_obs(source_row_id=None))
    assert state.source_row_id == f"a1b2c3@{_TS.isoformat()}"


def test_older_observation_without_new_fields_still_converts() -> None:
    """A record predating alt_geom_ft/on_ground/emitter_category/source_row_id."""
    old = SimpleNamespace(
        icao24="a1b2c3", observed_at=_TS, latitude=37.425, longitude=-79.215,
        altitude_ft=4850.0, ground_speed_kt=None, track_deg=None, callsign=None,
        squawk=None, nic=None, nacp=None,
    )
    state = observation_to_state(old)
    assert state.alt_geom_ft is None
    assert state.emitter_category is None
    assert state.on_ground is False
    assert state.source_row_id.startswith("a1b2c3@")


# ------------------------------------------------------------- construction

def test_build_detector_zero_args_loads_config_and_zones(detector: NoFlyZoneDetector) -> None:
    assert detector.detector_id == detector.cfg["detector"]["id"]
    assert detector.detector_version == detector.cfg["detector"]["version"]
    assert {z.zone_id for z in detector.zones} == {z.zone_id for z in load_zones(AIRSPACE_FILE)}


def test_build_detector_accepts_an_airspace_override() -> None:
    assert len(build_detector(airspace_path=AIRSPACE_FILE).zones) == len(load_zones(AIRSPACE_FILE))


def test_package_import_stays_light() -> None:
    """Importing the package must not pull in the heavy stages (shapely/h3).

    Checked in a fresh interpreter, because this test process has already
    imported every stage.
    """
    probe = (
        "import sys, air.detectors.no_fly_zone; "
        "heavy = [m for m in ('shapely', 'h3', 'contracts', "
        "'air.detectors.no_fly_zone.adapter') if m in sys.modules]; "
        "sys.exit(1 if heavy else 0)"
    )
    result = subprocess.run([sys.executable, "-c", probe], cwd=REPO_ROOT, check=False)
    assert result.returncode == 0


# ------------------------------------------------------------- behaviour

def test_fires_inside_zone_and_emits_platform_detection(detector: NoFlyZoneDetector) -> None:
    [detection] = detector.detect_observations([make_obs()])
    assert detection.geospatial_context.risk_zone_ids == ["P-901"]
    assert detection.provenance.raw_source_ref == "test.csv:7"
    assert [e.entity_id for e in detection.entities_involved] == ["aircraft:a1b2c3"]
    assert detection.temporal_bounds.start_time == _TS


def test_on_ground_aircraft_does_not_fire(detector: NoFlyZoneDetector) -> None:
    assert detector.detect_observations([make_obs(on_ground=True)]) == []
    assert detector.exit_counts[ExitReason.ON_GROUND] == 1


def test_outside_every_zone_does_not_fire(detector: NoFlyZoneDetector) -> None:
    assert detector.detect_observations([make_obs(latitude=36.0, longitude=-81.0)]) == []
    assert detector.exit_counts[ExitReason.NO_CANDIDATE] == 1


def test_geometric_altitude_is_used_when_baro_is_blank(detector: NoFlyZoneDetector) -> None:
    """The case the old shared contract could not express: ab blank, ag present."""
    assert len(detector.detect_observations([make_obs(altitude_ft=None)])) == 1


def test_no_altitude_at_all_abstains(detector: NoFlyZoneDetector) -> None:
    assert detector.detect_observations([make_obs(altitude_ft=None, alt_geom_ft=None)]) == []
    assert detector.exit_counts[ExitReason.BAD_INPUT] == 1


def test_detect_reads_observations_from_auxiliary_data(detector: NoFlyZoneDetector) -> None:
    context = DetectionContext(auxiliary_data={"observations": [make_obs()]})
    assert len(detector.detect(context)) == 1


# ------------------------------------------------------------- shared runner

def _load_replay_script() -> ModuleType:
    path = REPO_ROOT / "scripts" / "replay_csv.py"
    spec = importlib.util.spec_from_file_location("replay_csv_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_shared_runner_finds_the_detector() -> None:
    """The bug this adapter fixes: replay_csv.py used to skip NFZ."""
    replay = _load_replay_script()
    detector, reason = replay.load_detector("no_fly_zone")
    assert reason is None
    assert isinstance(detector, NoFlyZoneDetector)


def test_shared_path_matches_cli_path_on_fixture_track(detector: NoFlyZoneDetector) -> None:
    """Same rows, two routes in, identical detections out."""
    cli_states = list(load_states(TRACKS_FILE))
    cli_side = [
        to_platform_detection(d).to_dict()
        for d in run(cli_states, detector.zones, detector.cfg, exit_counts=Counter())
    ]

    rows = json.loads(TRACKS_FILE.read_text())
    observations = [
        AdsbObservation(
            icao24=row["icao24"], observed_at=row["timestamp"],
            latitude=row["lat"], longitude=row["lon"],
            altitude_ft=row.get("alt_baro_ft"), alt_geom_ft=row.get("alt_geom_ft"),
            ground_speed_kt=row.get("ground_speed_kt"), track_deg=row.get("track_deg"),
            callsign=row.get("callsign"), squawk=row.get("squawk"),
            emitter_category=row.get("emitter_category"),
            nic=row.get("nic"), nacp=row.get("nac_p"),
            on_ground=row.get("on_ground"), source_row_id=state.source_row_id,
        )
        for row, state in zip(rows, cli_states, strict=True)
    ]
    shared_side = [d.to_dict() for d in detector.detect_observations(observations)]

    def comparable(payloads: list[dict[str, Any]]) -> list[str]:
        out = []
        for payload in payloads:
            payload = json.loads(json.dumps(payload, default=str))
            payload.pop("detection_id")
            for evidence in payload["evidence"]:
                evidence.pop("evidence_id")
            out.append(json.dumps(payload, sort_keys=True))
        return sorted(out)

    assert cli_side, "fixture track should produce detections"
    assert comparable(shared_side) == comparable(cli_side)
