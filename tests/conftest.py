"""Shared test helpers.

`pythonpath = ["."]` in pyproject.toml already puts the repo root on sys.path,
so `import contracts` / `import air` work with a plain `pytest` from the root.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from air.models.observation import AdsbObservation

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "air" / "fixtures"


def load_observations(fixture_name: str) -> list[AdsbObservation]:
    """Load a fixture JSON file into AdsbObservation objects."""
    path = FIXTURES_DIR / fixture_name
    rows: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    return [AdsbObservation.from_dict(row) for row in rows]


@pytest.fixture
def observations_from():
    """Usage: `obs = observations_from('example_altitude.json')`."""
    return load_observations
