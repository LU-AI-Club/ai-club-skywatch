"""Stream Lead tests - logic/detector.py."""
from __future__ import annotations

from collections import Counter

from ..config import Config
from ..ingest.adsb_loader import load_states
from ..ingest.airspace_loader import load_zones
from ..logic.detector import run
from ..types import ExitReason
from .conftest import AIRSPACE_FILE, TRACKS_FILE, make_state


def test_fixture_track_yields_the_two_expected_detections(cfg: Config) -> None:
    """fixture-1 and fixture-3 fire; the other three exit. See fixtures/README.md."""
    exits: Counter[ExitReason] = Counter()
    detections = list(run(load_states(TRACKS_FILE), load_zones(AIRSPACE_FILE), cfg, exits))
    assert sorted(d.extras["zone_id"] for d in detections) == ["P-901", "TFR-6/1234"]
    assert sorted(d.extras["source_row_id"] for d in detections) == ["fixture-1", "fixture-3"]
    assert exits == Counter({
        ExitReason.VERTICAL_CLEAR: 1,
        ExitReason.ZONE_INACTIVE: 1,
        ExitReason.NO_CANDIDATE: 1,
    })


def test_on_ground_state_never_reaches_geometry(cfg: Config) -> None:
    """With filters.drop_on_ground true, a taxiing aircraft exits as ON_GROUND
    before any polygon test runs."""
    exits: Counter[ExitReason] = Counter()
    out = list(run([make_state(on_ground=True)], load_zones(AIRSPACE_FILE), cfg, exits))
    assert out == []
    assert exits == Counter({ExitReason.ON_GROUND: 1})
