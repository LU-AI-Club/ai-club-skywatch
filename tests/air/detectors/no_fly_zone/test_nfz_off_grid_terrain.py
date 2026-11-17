"""AGL floors where the terrain grid has no value.

The committed grid covers 65 nm around KLYH, and three AGL-floor zones reach
past it. There the floor is placed with the area-wide terrain bound
``geometry.off_grid_terrain_ft``: outside the range it allows the answer is
certain, inside it the detector still abstains.
"""
from __future__ import annotations

from typing import Any

import pytest
from nfz_support import FIXTURES, make_state
from shapely.geometry import Point, Polygon, box

from air.detectors.no_fly_zone.config import Config, _validate, load_config
from air.detectors.no_fly_zone.geo.altitude import terrain_elevation_ft, vertical_check
from air.detectors.no_fly_zone.geo.terrain import load_terrain
from air.detectors.no_fly_zone.ingest.airspace_loader import load_filtered_zones
from air.detectors.no_fly_zone.logic import detector as pipeline
from air.detectors.no_fly_zone.types import (
    Activation,
    AirspaceZone,
    Datum,
    ExitReason,
    TerrainGrid,
    ZoneType,
)

LIVE_AIRSPACE = FIXTURES / "airspace" / "klyh-local-faa.geojson"
BOUND = (300.0, 900.0)  # ground somewhere between 300 and 900 ft MSL

# A 2x2 grid nowhere near the test aircraft, so every lookup is off-grid.
FAR_GRID = TerrainGrid(
    lat_min=10.0, lon_min=10.0, lat_step=0.02, lon_step=0.02,
    elevations_ft=((500.0, 500.0), (500.0, 500.0)),
)


def _zone(**overrides: Any) -> AirspaceZone:
    """Floor 500 ft AGL, ceiling 6,000 ft MSL: with BOUND, the floor is 800-1,400 ft MSL."""
    base: dict[str, Any] = {
        "zone_id": "TEST MOA",
        "name": "TEST MOA",
        "zone_type": ZoneType.MOA,
        "geometry": Polygon(),
        "floor_ft": 500.0,
        "floor_datum": Datum.AGL,
        "ceiling_ft": 6000.0,
        "ceiling_datum": Datum.MSL,
        "activation": Activation.ALWAYS,
    }
    base.update(overrides)
    return AirspaceZone(**base)


def test_off_grid_fires_above_the_highest_the_floor_can_be() -> None:
    res = vertical_check(make_state(alt_geom_ft=1400.0), _zone(), FAR_GRID, BOUND)
    assert res.within is True
    assert res.altitude_ft == 1400.0


def test_off_grid_is_clear_below_the_lowest_the_floor_can_be() -> None:
    res = vertical_check(make_state(alt_geom_ft=799.0), _zone(), FAR_GRID, BOUND)
    assert res.within is False
    assert res.reason is ExitReason.VERTICAL_CLEAR


def test_off_grid_abstains_inside_the_range_the_floor_can_be_in() -> None:
    """At 1,000 ft MSL the aircraft is above the floor over low ground and
    below it over high ground."""
    res = vertical_check(make_state(alt_geom_ft=1000.0), _zone(), FAR_GRID, BOUND)
    assert res.within is False
    assert res.reason is ExitReason.BAD_INPUT


def test_off_grid_above_the_ceiling_is_clear_with_or_without_a_bound() -> None:
    for bound in (BOUND, None):
        res = vertical_check(make_state(alt_geom_ft=9000.0), _zone(), FAR_GRID, bound)
        assert res.within is False
        assert res.reason is ExitReason.VERTICAL_CLEAR


def test_off_grid_without_a_bound_still_abstains_under_the_ceiling() -> None:
    res = vertical_check(make_state(alt_geom_ft=3000.0), _zone(), FAR_GRID, None)
    assert res.within is False
    assert res.reason is ExitReason.BAD_INPUT


def test_the_bound_is_ignored_where_the_grid_has_a_value() -> None:
    """On the grid the ground is 500 ft, so the floor is exactly 1,000 ft MSL.
    1,100 ft is inside; the looser bound (floor up to 1,400) must not veto it."""
    grid = TerrainGrid(
        lat_min=37.0, lon_min=-80.0, lat_step=1.0, lon_step=1.0,
        elevations_ft=((500.0, 500.0), (500.0, 500.0)),
    )
    state = make_state(lat=37.4, lon=-79.2, alt_geom_ft=1100.0)
    assert vertical_check(state, _zone(), grid, BOUND).within is True


def test_off_grid_barometric_only_uses_barometric() -> None:
    state = make_state(alt_geom_ft=None, alt_baro_ft=2000.0)
    assert vertical_check(state, _zone(), FAR_GRID, BOUND).within is True


@pytest.mark.parametrize("bound", [{"min": 100}, {"min": 900, "max": 300}, [0, 5800]])
def test_config_rejects_a_bad_off_grid_bound(bound: Any) -> None:
    raw = dict(load_config().raw)
    raw["geometry"] = {**raw["geometry"], "off_grid_terrain_ft": bound}
    with pytest.raises(ValueError, match="off_grid_terrain_ft"):
        _validate(raw)


# --- the real zones and the real grid ------------------------------------------


def _off_grid_point(zone: AirspaceZone, grid: TerrainGrid) -> Point:
    """A point inside ``zone`` that the committed grid does not cover."""
    rows, columns = len(grid.elevations_ft), len(grid.elevations_ft[0])
    covered = box(
        grid.lon_min,
        grid.lat_min,
        grid.lon_min + (columns - 1) * grid.lon_step,
        grid.lat_min + (rows - 1) * grid.lat_step,
    )
    point = zone.geometry.difference(covered).representative_point()
    assert terrain_elevation_ft(grid, point.y, point.x) is None
    return point


def _fired(zone_id: str, altitude_ft: float, cfg: Config) -> set[str]:
    grid = load_terrain()
    zones = load_filtered_zones(LIVE_AIRSPACE, cfg)
    zone = next(z for z in zones if z.zone_id == zone_id)
    point = _off_grid_point(zone, grid)
    state = make_state(lat=point.y, lon=point.x, alt_geom_ft=altitude_ft, alt_baro_ft=altitude_ft)
    return {d.extras["zone_id"] for d in pipeline.run([state], zones, cfg, terrain=grid)}


def test_evers_east_fires_off_the_grid_when_clearly_above_its_floor() -> None:
    """Floor 1,000 ft AGL. At 9,000 ft MSL the aircraft is above it over any
    ground in Virginia or West Virginia, and below the FL180 ceiling."""
    assert "EVERS EAST MOA" in _fired("EVERS EAST MOA", 9000.0, load_config())


def test_evers_east_abstains_off_the_grid_where_the_floor_cannot_be_placed() -> None:
    assert "EVERS EAST MOA" not in _fired("EVERS EAST MOA", 3000.0, load_config())


def test_without_the_bound_evers_east_never_fires_off_the_grid() -> None:
    raw = dict(load_config().raw)
    raw["geometry"] = {k: v for k, v in raw["geometry"].items() if k != "off_grid_terrain_ft"}
    assert "EVERS EAST MOA" not in _fired("EVERS EAST MOA", 9000.0, Config(raw))
