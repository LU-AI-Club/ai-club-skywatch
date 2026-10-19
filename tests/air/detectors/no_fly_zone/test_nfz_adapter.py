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
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
from nfz_support import AIRSPACE_FILE, TRACKS_FILE

from air.detectors.no_fly_zone import build_detector
from air.detectors.no_fly_zone.adapter import NoFlyZoneDetector, observation_to_state
from air.detectors.no_fly_zone.emit import to_platform_detection
from air.detectors.no_fly_zone.ingest.airspace_loader import load_zones
from air.detectors.no_fly_zone.logic.detector import run
from air.detectors.no_fly_zone.types import AircraftState, ExitReason
from air.models.observation import AdsbObservation
from air.normalizers.no_fly_zone_adsb import load_states
from contracts import DetectionContext

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
    # The incursion is still open when the window ends, so it comes out on flush.
    assert detector.detect_observations([make_obs()]) == []
    assert detector.open_episodes == 1
    [detection] = detector.flush()
    assert detector.open_episodes == 0
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
    detector.detect_observations([make_obs(altitude_ft=None)])
    assert len(detector.flush()) == 1


def test_no_altitude_at_all_abstains(detector: NoFlyZoneDetector) -> None:
    assert detector.detect_observations([make_obs(altitude_ft=None, alt_geom_ft=None)]) == []
    assert detector.exit_counts[ExitReason.BAD_INPUT] == 1


def test_detect_reads_observations_from_auxiliary_data(detector: NoFlyZoneDetector) -> None:
    context = DetectionContext(auxiliary_data={"observations": [make_obs()]})
    assert detector.detect(context) == []
    assert detector.open_episodes == 1


def test_detect_flushes_when_the_caller_asks(detector: NoFlyZoneDetector) -> None:
    """A one-shot SENTINEL call sets parameters['flush'] to get open episodes too."""
    context = DetectionContext(
        auxiliary_data={"observations": [make_obs()]}, parameters={"flush": True}
    )
    assert len(detector.detect(context)) == 1
    assert detector.open_episodes == 0


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
    shared = detector.detect_observations(observations) + detector.flush()
    shared_side = [d.to_dict() for d in shared]

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


# ------------------------------------------------- episodes across windows

CROSSINGS_FILE = TRACKS_FILE.parent / "lynchburg_crossings.csv"


def _comparable(detections: list[Any]) -> list[str]:
    """Platform detections minus their random ids, sorted, for equality checks."""
    out = []
    for detection in detections:
        payload = json.loads(json.dumps(detection.to_dict(), default=str))
        payload.pop("detection_id")
        for evidence in payload["evidence"]:
            evidence.pop("evidence_id")
        out.append(json.dumps(payload, sort_keys=True))
    return sorted(out)


def _as_observation(state: AircraftState) -> AdsbObservation:
    """The shared-runner record for one row, built from NFZ's own loader."""
    return AdsbObservation(
        icao24=state.icao24, observed_at=state.timestamp,
        latitude=state.lat, longitude=state.lon,
        altitude_ft=state.alt_baro_ft, alt_geom_ft=state.alt_geom_ft,
        ground_speed_kt=state.ground_speed_kt, track_deg=state.track_deg,
        callsign=state.callsign, squawk=state.squawk,
        emitter_category=state.emitter_category, nic=state.nic, nacp=state.nac_p,
        on_ground=state.on_ground, source_row_id=state.source_row_id,
    )


def _cli_crossings(detector: NoFlyZoneDetector) -> list[str]:
    cli = run(load_states(CROSSINGS_FILE), detector.zones, detector.cfg, exit_counts=Counter())
    return _comparable([to_platform_detection(d) for d in cli])


@pytest.mark.parametrize(("window_s", "step_s"), [(60, 60), (10, 10), (60, 20), (3600, 3600)])
def test_windowed_route_matches_cli_at_any_window_size(window_s: int, step_s: int) -> None:
    """The CI parity bug: PDT5877's 41 s crossing spans the 00:55:00 window edge.

    Before episodes survived window edges, 60 s windows turned that one
    crossing into two detections. Tumbling and sliding windows must now give
    exactly what the CLI gives.
    """
    from air.windowing import iter_windows, run_detectors

    detector = build_detector()
    observations = [_as_observation(state) for state in load_states(CROSSINGS_FILE)]
    windows = iter_windows(observations, window_s, step_s)
    shared = list(run_detectors(windows, [detector], dedup=step_s < window_s))

    expected = _cli_crossings(detector)
    assert len(expected) == 2
    assert _comparable(shared) == expected
    assert detector.open_episodes == 0


def test_episode_open_at_a_window_edge_is_held_not_emitted(detector: NoFlyZoneDetector) -> None:
    first = make_obs(observed_at=_TS)
    second = make_obs(observed_at=_TS + timedelta(seconds=5), source_row_id="test.csv:8")
    assert detector.detect_observations([first]) == []
    assert detector.detect_observations([second]) == []
    [episode] = detector.flush()
    assert episode.metadata["extras"]["report_count"] == 2
    assert episode.temporal_bounds.end_time == _TS + timedelta(seconds=5)


def test_silence_closes_an_episode_in_a_later_window(detector: NoFlyZoneDetector) -> None:
    """The aircraft stops reporting; another aircraft moves the stream clock on."""
    max_gap = float(detector.cfg["sampling"]["max_gap_sec"])
    assert detector.detect_observations([make_obs()]) == []
    later = make_obs(
        icao24="ffffff", latitude=36.0, longitude=-81.0, source_row_id="test.csv:9",
        observed_at=_TS + timedelta(seconds=max_gap + 1),
    )
    [closed] = detector.detect_observations([later])
    assert [e.entity_id for e in closed.entities_involved] == ["aircraft:a1b2c3"]
    assert detector.open_episodes == 0


def test_two_clear_reports_close_an_episode_in_a_later_window(detector: NoFlyZoneDetector) -> None:
    assert detector.detect_observations([make_obs()]) == []
    clear = [
        make_obs(latitude=36.0, longitude=-81.0, observed_at=_TS + timedelta(seconds=s),
                 source_row_id=f"test.csv:{10 + s}")
        for s in (1, 2)
    ]
    assert len(detector.detect_observations(clear)) == 1
    assert detector.open_episodes == 0


def test_overlapping_windows_never_feed_a_report_twice(detector: NoFlyZoneDetector) -> None:
    obs = make_obs()
    detector.detect_observations([obs])
    detector.detect_observations([obs])
    assert detector.skipped_reports == 1
    [episode] = detector.flush()
    assert episode.metadata["extras"]["report_count"] == 1


def test_replay_runner_flushes_nfz_after_the_last_window(tmp_path: Path) -> None:
    """scripts/replay_csv.py emits episodes still open when the data ends."""
    rows = CROSSINGS_FILE.read_text().splitlines()
    header, body = rows[0], rows[1:]
    # Cut the file right after PDT5877's last firing report, so its episode is
    # still open when the stream ends and only flush() can emit it.
    cut = next(i for i, line in enumerate(body) if "00:55:27" in line) + 1
    truncated = tmp_path / "cut.csv"
    truncated.write_text("\n".join([header, *body[:cut]]) + "\n")

    out = tmp_path / "replay.jsonl"
    replay = _load_replay_script()
    args = [str(truncated), "--detector", "no_fly_zone", "--out", str(out), "--quiet"]
    assert replay.main(args) == 0
    lines = out.read_text().splitlines()
    entities = sorted(json.loads(line)["entities_involved"][0]["entity_id"] for line in lines)
    assert entities == ["aircraft:a89076", "aircraft:ac8438"]


def test_run_detectors_flushes_after_the_last_window(detector: NoFlyZoneDetector) -> None:
    """air.windowing.run_detectors, the live-loop helper, flushes like the runner."""
    from air.windowing import run_detectors

    [episode] = list(run_detectors([[make_obs()]], [detector]))
    assert [e.entity_id for e in episode.entities_involved] == ["aircraft:a1b2c3"]
