"""Load the committed, offline terrain grid used by the altitude stage."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from ..types import TerrainGrid

DEFAULT_TERRAIN_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "terrain" / "klyh-65nm.json"
)


def load_terrain(path: str | Path = DEFAULT_TERRAIN_PATH) -> TerrainGrid:
    """Load a validated terrain grid from JSON.

    The file is read only when this function is called, allowing detector
    construction to load it once and pass the immutable grid through the
    pipeline.
    """
    terrain_path = Path(path)
    if not terrain_path.is_file():
        raise FileNotFoundError(f"terrain grid not found: {terrain_path}")
    with terrain_path.open("r", encoding="utf-8") as file:
        raw: Any = json.load(file)

    lat_min = float(raw["lat_min"])
    lon_min = float(raw["lon_min"])
    lat_step = float(raw["lat_step"])
    lon_step = float(raw["lon_step"])
    if not all(math.isfinite(value) for value in (lat_min, lon_min, lat_step, lon_step)):
        raise ValueError("terrain grid origin and spacing must be finite")
    if lat_step <= 0 or lon_step <= 0:
        raise ValueError("terrain grid spacing must be positive")

    raw_rows = raw["elevations_ft"]
    if not isinstance(raw_rows, list) or len(raw_rows) < 2:
        raise ValueError("terrain grid must contain at least two rows")
    if any(not isinstance(row, list) or len(row) < 2 for row in raw_rows):
        raise ValueError("terrain grid must contain at least two columns per row")
    width = len(raw_rows[0])
    if any(len(row) != width for row in raw_rows):
        raise ValueError("terrain grid rows must have the same number of columns")

    elevations: list[tuple[float | None, ...]] = []
    for row in raw_rows:
        values: list[float | None] = []
        for value in row:
            if value is None:
                values.append(None)
                continue
            elevation = float(value)
            if not math.isfinite(elevation):
                raise ValueError("terrain elevations must be finite or null")
            values.append(elevation)
        elevations.append(tuple(values))

    return TerrainGrid(
        lat_min=lat_min,
        lon_min=lon_min,
        lat_step=lat_step,
        lon_step=lon_step,
        elevations_ft=tuple(elevations),
    )
