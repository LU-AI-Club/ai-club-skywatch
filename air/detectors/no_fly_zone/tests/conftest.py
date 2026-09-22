"""Shared fixtures for the no_fly_zone test suite.

Paths and builders only - no assertions, and no I/O at import time.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from ..config import Config, load_config
from ..types import AircraftState

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
AIRSPACE_FILE = FIXTURES / "airspace" / "klyh-150nm.geojson"
TRACKS_FILE = FIXTURES / "tracks" / "klyh_mixed.json"

# Annotation keys the fixture rows carry that are not AircraftState fields.
_ANNOTATIONS = ("_label", "_expect")


@pytest.fixture
def cfg() -> Config:
    """The packaged config, loaded fresh per test."""
    return load_config()


@pytest.fixture
def raw_tracks() -> list[dict[str, Any]]:
    """The five fixture rows as plain dicts, annotations included."""
    rows: list[dict[str, Any]] = json.loads(TRACKS_FILE.read_text())
    return rows


def make_state(**overrides: Any) -> AircraftState:
    """Build an AircraftState, overriding any field.

    Defaults place the aircraft inside fixture zone P-901 below its ceiling -
    the firing case. Override fields to build the non-firing ones.
    """
    base: dict[str, Any] = {
        "icao24": "a1b2c3",
        "timestamp": datetime(2026, 9, 22, 20, 15, tzinfo=UTC),
        "lat": 37.425,
        "lon": -79.215,
        "alt_baro_ft": 4850.0,
        "alt_geom_ft": 5200.0,
        "ground_speed_kt": 186.7,
        "track_deg": 4.9,
        "callsign": "TEST123",
        "squawk": "1200",
        "emitter_category": "A3",
        "nic": 8,
        "nac_p": 9,
        "on_ground": False,
        "source_row_id": "test-1",
    }
    base.update({k: v for k, v in overrides.items() if k not in _ANNOTATIONS})
    return AircraftState(**base)
