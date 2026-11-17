"""Fixture-backed tests for the committed offline terrain grid."""
from __future__ import annotations

from air.detectors.no_fly_zone.geo.altitude import terrain_elevation_ft
from air.detectors.no_fly_zone.geo.terrain import DEFAULT_TERRAIN_PATH, load_terrain
from air.detectors.no_fly_zone.types import TerrainGrid


def test_committed_terrain_grid_covers_its_edges() -> None:
    grid = load_terrain(DEFAULT_TERRAIN_PATH)

    assert terrain_elevation_ft(grid, grid.lat_min, grid.lon_min) is not None
    assert terrain_elevation_ft(
        grid,
        grid.lat_min + (len(grid.elevations_ft) - 1) * grid.lat_step,
        grid.lon_min + (len(grid.elevations_ft[0]) - 1) * grid.lon_step,
    ) is not None
    assert terrain_elevation_ft(grid, grid.lat_min - grid.lat_step, grid.lon_min) is None


def test_unknown_terrain_cell_is_not_interpolated() -> None:
    grid = TerrainGrid(
        lat_min=37.0,
        lon_min=-80.0,
        lat_step=0.1,
        lon_step=0.1,
        elevations_ft=((100.0, 100.0), (100.0, None)),
    )

    assert terrain_elevation_ft(grid, 37.05, -79.95) is None
