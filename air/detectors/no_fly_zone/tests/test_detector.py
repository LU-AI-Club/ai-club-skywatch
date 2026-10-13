"""Stream Lead tests - logic/detector.py.

Stream C (zone_index + containment) may not have landed yet, so most tests
swap in ``_FakeStreamC``: a plain shapely point-in-polygon. That isolates the
*wiring* - stage order, exit reasons, one Detection per zone - from geometry,
which stream C owns and tests itself.

``test_fixture_track_with_real_stream_c`` runs the same assertions through the
real stream C, and skips itself until C stops raising NotImplementedError.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from typing import Any

import pytest

from ..config import Config
from ..geo import containment, zone_index
from ..ingest.adsb_loader import load_states
from ..ingest.airspace_loader import load_zones
from ..logic.detector import run
from ..types import Activation, ContainmentResult, ExitReason, Severity
from .conftest import AIRSPACE_FILE, TRACKS_FILE, make_state

shapely_geometry = pytest.importorskip("shapely.geometry")

# Degrees of padding for the fake coarse filter (~3 nm). Recall only.
_FAKE_PAD_DEG = 0.05


class _FakeStreamC:
    """Minimal stand-in for stream C, good enough to exercise the wiring."""

    @staticmethod
    def candidate_zone_ids(state: Any, zones: Any, cfg: Config) -> tuple[str, ...]:
        point = shapely_geometry.Point(state.lon, state.lat)
        return tuple(
            z.zone_id for z in zones if z.geometry.buffer(_FAKE_PAD_DEG).contains(point)
        )

    @staticmethod
    def check_containment(state: Any, zones: Any, cfg: Config) -> ContainmentResult:
        point = shapely_geometry.Point(state.lon, state.lat)
        hits = tuple(z.zone_id for z in zones if z.geometry.contains(point))
        if not hits:
            return ContainmentResult(
                False, False, (), None, None, reason=ExitReason.OUTSIDE_POLYGON
            )
        depth_deg = min(z.geometry.exterior.distance(point) for z in zones)
        return ContainmentResult(True, True, hits, depth_deg * 60.0, None)


@pytest.fixture
def fake_c(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(zone_index, "candidate_zone_ids", _FakeStreamC.candidate_zone_ids)
    monkeypatch.setattr(containment, "check_containment", _FakeStreamC.check_containment)


def _assert_fixture_outcome(cfg: Config) -> None:
    """fixture-1 and fixture-3 fire; 2, 4 and 5 exit. See fixtures/README.md."""
    exits: Counter[ExitReason] = Counter()
    detections = list(
        run(load_states(TRACKS_FILE), load_zones(AIRSPACE_FILE), cfg, exit_counts=exits)
    )

    fired = sorted((d.extras["source_row_id"], d.extras["zone_id"]) for d in detections)
    assert fired == [("fixture-1", "P-901"), ("fixture-3", "TFR-6/1234")]
    assert exits == Counter({
        ExitReason.VERTICAL_CLEAR: 1,   # fixture-2, over P-901 at FL350
        ExitReason.ZONE_INACTIVE: 1,    # fixture-4, TFR window shut
        ExitReason.NO_CANDIDATE: 1,     # fixture-5, clear of everything
    })


def test_fixture_track_yields_the_two_expected_detections(cfg: Config, fake_c: None) -> None:
    _assert_fixture_outcome(cfg)


def test_fixture_track_with_real_stream_c(cfg: Config) -> None:
    try:
        zone_index.candidate_zone_ids(make_state(), [], cfg)
    except NotImplementedError:
        pytest.skip("stream C not implemented yet - covered by the fake-C test")
    _assert_fixture_outcome(cfg)


def test_on_ground_state_never_reaches_geometry(
    cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*_: Any) -> None:
        raise AssertionError("geometry ran for an on-ground state")

    monkeypatch.setattr(zone_index, "candidate_zone_ids", explode)
    exits: Counter[ExitReason] = Counter()
    zones = load_zones(AIRSPACE_FILE)

    assert list(run([make_state(on_ground=True)], zones, cfg, exit_counts=exits)) == []
    assert exits == Counter({ExitReason.ON_GROUND: 1})


def test_unknown_activation_still_emits_but_capped(cfg: Config, fake_c: None) -> None:
    """A NOTAM zone we cannot resolve is not a pass: it fires, at the capped severity."""
    zones = [
        replace(z, activation=Activation.NOTAM) if z.zone_id == "P-901" else z
        for z in load_zones(AIRSPACE_FILE)
    ]
    (detection,) = list(run([make_state()], zones, cfg))

    assert detection.extras["zone_id"] == "P-901"
    assert detection.severity is Severity(cfg["severity"]["unknown_activation_cap"])
    assert detection.raw_model_confidence == 0.0


def test_no_altitude_exits_as_bad_input(cfg: Config, fake_c: None) -> None:
    exits: Counter[ExitReason] = Counter()
    state = make_state(alt_baro_ft=None, alt_geom_ft=None)

    assert list(run([state], load_zones(AIRSPACE_FILE), cfg, exit_counts=exits)) == []
    assert exits == Counter({ExitReason.BAD_INPUT: 1})


def test_counter_is_optional(cfg: Config, fake_c: None) -> None:
    """Callers that do not care about exits (the CLI's old call) still work."""
    assert len(list(run([make_state()], load_zones(AIRSPACE_FILE), cfg))) == 1
