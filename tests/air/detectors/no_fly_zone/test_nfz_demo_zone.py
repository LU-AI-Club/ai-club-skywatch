"""The synthetic demo zone (DEMO-1) for live demos and frontend testing.

build_live_detector adds the zones at airspace.demo_path on top of the real
zones only when asked (demo_zones=True or SKYWATCH_NFZ_DEMO_ZONES=1). It must be
off by default, never reach replay/tests/the CLI, never look like real
airspace, and fire on real local traffic.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

pytest.importorskip("shapely")
pytest.importorskip("h3")

from air.detectors.no_fly_zone import (  # noqa: E402
    DEMO_ZONES_ENV,
    build_detector,
    build_live_detector,
)
from air.detectors.no_fly_zone.adapter import (  # noqa: E402
    NoFlyZoneDetector,
    demo_airspace_path,
    live_airspace_path,
)
from air.detectors.no_fly_zone.config import DEFAULT_PATH, load_config  # noqa: E402
from air.models.observation import AdsbObservation  # noqa: E402

_TS = datetime(2026, 9, 22, 20, 15, tzinfo=UTC)
# Centre of DEMO-1: 3 nm west of KLYH.
_DEMO_LAT, _DEMO_LON = 37.3184, -79.2628


def _ids(detector: NoFlyZoneDetector) -> set[str]:
    return {zone.zone_id for zone in detector.zones}


def _real_ids() -> set[str]:
    path = live_airspace_path(load_config(DEFAULT_PATH))
    assert path is not None
    data = json.loads(path.read_text(encoding="utf-8"))
    return {f["properties"]["zone_id"] for f in data["features"]}


def _obs(seconds: int, *, lat: float = _DEMO_LAT, alt_ft: float = 3000.0) -> AdsbObservation:
    return AdsbObservation(
        icao24="a1b2c3", observed_at=_TS + timedelta(seconds=seconds),
        latitude=lat, longitude=_DEMO_LON, altitude_ft=alt_ft, alt_geom_ft=alt_ft,
        ground_speed_kt=110.0, track_deg=90.0, callsign="DEMO1", squawk="1200",
        emitter_category="A1", nic=8, nacp=9, on_ground=False,
        source_row_id=f"test.csv:demo{seconds}",
    )


@pytest.fixture(autouse=True)
def _no_demo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test starts with the switch unset, whatever the shell has."""
    monkeypatch.delenv(DEMO_ZONES_ENV, raising=False)


def test_demo_zone_is_off_by_default() -> None:
    assert _ids(build_live_detector()) == _real_ids()


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_env_switch_adds_the_demo_zone_on_top_of_the_real_ones(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, value: str,
) -> None:
    monkeypatch.setenv(DEMO_ZONES_ENV, value)
    with caplog.at_level(logging.WARNING, logger="air.detectors.no_fly_zone"):
        ids = _ids(build_live_detector())
    assert ids == _real_ids() | {"DEMO-1"}
    assert "DEMO zones ON (DEMO-1" in caplog.text
    assert "NOT real airspace" in caplog.text


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_other_env_values_leave_it_off(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(DEMO_ZONES_ENV, value)
    assert "DEMO-1" not in _ids(build_live_detector())


def test_argument_overrides_the_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert "DEMO-1" in _ids(build_live_detector(demo_zones=True))
    monkeypatch.setenv(DEMO_ZONES_ENV, "1")
    assert "DEMO-1" not in _ids(build_live_detector(demo_zones=False))


def test_replay_and_cli_builder_never_load_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DEMO_ZONES_ENV, "1")
    assert "DEMO-1" not in _ids(build_detector())


def test_demo_file_only_holds_clearly_labelled_synthetic_zones() -> None:
    path = demo_airspace_path(load_config(DEFAULT_PATH))
    assert path is not None and path.is_file()
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    assert features
    for feature in features:
        props = feature["properties"]
        assert props["zone_id"].startswith("DEMO-")
        assert props["source"] == "demo"
        assert "not real airspace" in props["name"]
    assert not {f["properties"]["zone_id"] for f in features} & _real_ids()


def test_clashing_zone_ids_fail_loudly(tmp_path: Path) -> None:
    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["airspace"]["demo_path"] = raw["airspace"]["live_path"]   # every id clashes
    cfg = tmp_path / "nfz.yaml"
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="clash"):
        build_live_detector(cfg, demo_zones=True)


def test_missing_demo_path_fails_loudly(tmp_path: Path) -> None:
    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    del raw["airspace"]["demo_path"]
    cfg = tmp_path / "nfz.yaml"
    cfg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match="demo_path"):
        build_live_detector(cfg, demo_zones=True)


def test_aircraft_inside_the_demo_zone_is_a_high_open_incursion() -> None:
    [det] = build_live_detector(demo_zones=True).detect_observations([_obs(0), _obs(1)])
    assert det.metadata["extras"]["zone_id"] == "DEMO-1"
    assert det.severity.value == "HIGH"
    assert det.entities_involved[0].entity_id == "icao24:a1b2c3"


def test_aircraft_above_the_demo_ceiling_does_not_fire() -> None:
    detector = build_live_detector(demo_zones=True)
    assert detector.detect_observations([_obs(0, alt_ft=7000.0), _obs(1, alt_ft=7000.0)]) == []


def test_aircraft_outside_the_demo_zone_does_not_fire() -> None:
    detector = build_live_detector(demo_zones=True)
    far = _DEMO_LAT + 0.05      # 3 nm north, clear of every zone
    assert detector.detect_observations([_obs(0, lat=far), _obs(1, lat=far)]) == []
