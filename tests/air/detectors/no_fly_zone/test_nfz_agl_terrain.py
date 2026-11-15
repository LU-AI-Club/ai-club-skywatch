"""NFZ-12E - AGL-floor zones can fire, using a terrain bound.

Loader side (the bound on a feature, the config fallback) and one pass through
the whole pipeline on the real FAA zones. The vertical rule itself is tested in
test_nfz_altitude.py.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from nfz_support import FIXTURES, make_state

from air.detectors.no_fly_zone.config import Config, _validate, load_config
from air.detectors.no_fly_zone.geo.altitude import vertical_check
from air.detectors.no_fly_zone.ingest.airspace_loader import (
    apply_terrain_fallback,
    load_filtered_zones,
    load_zones,
)
from air.detectors.no_fly_zone.logic import detector as pipeline
from air.detectors.no_fly_zone.types import Datum, ExitReason

LIVE_AIRSPACE = FIXTURES / "airspace" / "klyh-local-faa.geojson"
SQUARE = [[[-79.3, 37.3], [-79.1, 37.3], [-79.1, 37.5], [-79.3, 37.5], [-79.3, 37.3]]]


def _write(tmp_path: Path, **props: Any) -> Path:
    base: dict[str, Any] = {
        "zone_id": "TEST MOA",
        "zone_type": "MOA",
        "activation": "ALWAYS",
        "floor_ft": 500,
        "floor_datum": "AGL",
        "ceiling_ft": 6000,
        "ceiling_datum": "MSL",
    }
    base.update(props)
    feature = {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": SQUARE},
        "properties": base,
    }
    path = tmp_path / "zones.geojson"
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))
    return path


def _cfg(terrain: dict[str, float] | None) -> Config:
    raw = dict(load_config().raw)
    geometry = dict(raw["geometry"])
    geometry.pop("terrain_fallback_ft", None)
    if terrain is not None:
        geometry["terrain_fallback_ft"] = terrain
    raw["geometry"] = geometry
    return Config(raw)


def test_loader_reads_a_zone_terrain_bound(tmp_path: Path) -> None:
    [zone] = load_zones(_write(tmp_path, terrain_min_ft=300, terrain_max_ft=900))
    assert (zone.terrain_min_ft, zone.terrain_max_ft) == (300.0, 900.0)


def test_loader_leaves_terrain_unknown_when_absent(tmp_path: Path) -> None:
    [zone] = load_zones(_write(tmp_path))
    assert (zone.terrain_min_ft, zone.terrain_max_ft) == (None, None)


@pytest.mark.parametrize(
    "props",
    [
        {"terrain_min_ft": 300},
        {"terrain_max_ft": 900},
        {"terrain_min_ft": 900, "terrain_max_ft": 300},
    ],
)
def test_loader_rejects_a_bad_terrain_bound(tmp_path: Path, props: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="terrain"):
        load_zones(_write(tmp_path, **props))


def test_fallback_fills_agl_zones_that_have_no_bound(tmp_path: Path) -> None:
    [zone] = load_filtered_zones(_write(tmp_path), _cfg({"min": 0, "max": 5800}))
    assert (zone.terrain_min_ft, zone.terrain_max_ft) == (0.0, 5800.0)


def test_a_zone_bound_wins_over_the_fallback(tmp_path: Path) -> None:
    path = _write(tmp_path, terrain_min_ft=300, terrain_max_ft=900)
    [zone] = load_filtered_zones(path, _cfg({"min": 0, "max": 5800}))
    assert (zone.terrain_min_ft, zone.terrain_max_ft) == (300.0, 900.0)


def test_fallback_leaves_zones_without_agl_limits_alone(tmp_path: Path) -> None:
    path = _write(tmp_path, floor_ft=4000, floor_datum="MSL")
    [zone] = load_filtered_zones(path, _cfg({"min": 0, "max": 5800}))
    assert zone.terrain_min_ft is None


def test_no_fallback_configured_changes_nothing(tmp_path: Path) -> None:
    zones = load_zones(_write(tmp_path))
    assert apply_terrain_fallback(zones, _cfg(None)) == zones


@pytest.mark.parametrize("terrain", [{"min": 100}, {"min": 900, "max": 300}, [0, 5800]])
def test_config_rejects_a_bad_fallback(terrain: Any) -> None:
    with pytest.raises(ValueError, match="terrain_fallback_ft"):
        _validate(_cfg(terrain).raw)


# --- the real FAA zones, end to end --------------------------------------------


def _report_in(zone_id: str, altitude_ft: float) -> tuple[Any, list[Any], Config]:
    """One airborne report at ``altitude_ft`` inside real zone ``zone_id``."""
    cfg = load_config()
    zones = load_filtered_zones(LIVE_AIRSPACE, cfg)
    zone = next(z for z in zones if z.zone_id == zone_id)
    assert zone.floor_datum is Datum.AGL
    point = zone.geometry.representative_point()
    state = make_state(
        lat=point.y,
        lon=point.x,
        alt_geom_ft=altitude_ft,
        alt_baro_ft=altitude_ft,
        timestamp=datetime(2026, 11, 15, 12, 0, tzinfo=UTC),
    )
    return state, zones, cfg


def test_evers_low_fires_well_above_its_agl_floor() -> None:
    """Floor 1,000 ft AGL: at 8,000 ft MSL the aircraft is above it over any
    ground in the area, and below the 11,000 ft ceiling."""
    state, zones, cfg = _report_in("EVERS LOW MOA", 8000.0)
    fired = {d.extras["zone_id"] for d in pipeline.run([state], zones, cfg)}
    assert "EVERS LOW MOA" in fired


def test_evers_low_abstains_where_the_floor_cannot_be_placed() -> None:
    """At 3,000 ft MSL the 1,000 ft AGL floor could be above or below the aircraft."""
    state, zones, cfg = _report_in("EVERS LOW MOA", 3000.0)
    fired = {d.extras["zone_id"] for d in pipeline.run([state], zones, cfg)}
    assert "EVERS LOW MOA" not in fired
    zone = next(z for z in zones if z.zone_id == "EVERS LOW MOA")
    assert vertical_check(state, zone).reason is ExitReason.BAD_INPUT


def test_detection_says_the_floor_came_from_a_terrain_bound() -> None:
    cfg = load_config()
    zones = load_filtered_zones(LIVE_AIRSPACE, cfg)
    zone = next(z for z in zones if z.zone_id == "EVERS LOW MOA")
    point = zone.geometry.representative_point()
    state = make_state(lat=point.y, lon=point.x, alt_geom_ft=8000.0, alt_baro_ft=8000.0)
    [detection] = [
        d for d in pipeline.run([state], zones, cfg) if d.extras["zone_id"] == "EVERS LOW MOA"
    ]
    assert any("terrain bound (0-5800 ft MSL)" in text for text in detection.limitations)
