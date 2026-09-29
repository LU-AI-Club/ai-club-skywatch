"""Stream A tests - ingest/adsb_loader.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..ingest.adsb_loader import load_states
from .conftest import TRACKS_FILE

REPO_CSV = Path(__file__).resolve().parents[4] / "data" / "lynchburg_adsb.csv"


def test_loads_every_usable_row() -> None:
    """Five fixture rows in, five AircraftState out, annotation keys ignored."""
    states = list(load_states(TRACKS_FILE))
    assert len(states) == 5
    assert states[0].icao24 == "a1b2c3"
    assert states[0].timestamp.tzinfo is not None
    assert states[0].source_row_id == "fixture-1"


def test_skips_a_row_with_no_position(tmp_path: Path) -> None:
    """A row missing lat/lon is skipped, not raised on - one bad row must not
    kill an hour of data."""
    rows = json.loads(TRACKS_FILE.read_text())
    rows[1]["lat"] = None
    path = tmp_path / "tracks.json"
    path.write_text(json.dumps(rows))
    ids = [s.source_row_id for s in load_states(path)]
    assert ids == ["fixture-1", "fixture-3", "fixture-4", "fixture-5"]


def test_refuses_a_naive_timestamp(tmp_path: Path) -> None:
    """A timestamp with no zone is not silently taken as UTC."""
    rows = json.loads(TRACKS_FILE.read_text())[:1]
    rows[0]["timestamp"] = "2026-09-22T20:15:00"
    path = tmp_path / "naive.json"
    path.write_text(json.dumps(rows))
    with pytest.raises(ValueError, match="no timezone"):
        list(load_states(path))


@pytest.mark.skipif(not REPO_CSV.exists(), reason="sample CSV not present")
def test_reads_the_abbreviated_csv_columns() -> None:
    """The sample CSV maps h/la/lo/ab/ag and keeps provenance to the line."""
    first = next(iter(load_states(REPO_CSV)))
    assert first.icao24 == "ace81d"
    assert first.alt_geom_ft == 5200.0
    assert first.callsign == "AAL1715"
    assert first.nic == 8
    assert first.source_row_id == "lynchburg_adsb.csv:2"
