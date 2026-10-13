"""Stream C (part 1) tests - geo/zone_index.py H3 coarse filter."""
from __future__ import annotations

from typing import Any

import pytest
from shapely.geometry import box

from ..config import Config
from ..geo.zone_index import candidate_zone_ids
from ..types import Activation, AirspaceZone, Datum, ZoneType
from .conftest import make_state


def make_zone(zone_id: str, west: float, south: float, east: float, north: float) -> AirspaceZone:
    return AirspaceZone(
        zone_id=zone_id, name=zone_id, zone_type=ZoneType.PROHIBITED,
        geometry=box(west, south, east, north),
        floor_ft=0, floor_datum=Datum.SFC, ceiling_ft=18000, ceiling_datum=Datum.MSL,
        activation=Activation.ALWAYS,
    )


P_901 = make_zone("P-901", -79.25, 37.40, -79.18, 37.45)
TFR = make_zone("TFR-6/1234", -79.30, 37.20, -79.22, 37.26)
MOA = make_zone("LYNCHBURG-MOA", -79.70, 37.30, -79.45, 37.50)
ZONES = [P_901, TFR, MOA]


def test_firing_state_inside_p901_is_a_candidate(cfg: Config) -> None:
    """The default state sits inside P-901."""
    assert candidate_zone_ids(make_state(), ZONES, cfg) == ("P-901",)


def test_clear_state_has_no_candidates(cfg: Config) -> None:
    """East of KLYH, nowhere near any zone: empty is a normal result."""
    assert candidate_zone_ids(make_state(lat=37.10, lon=-78.80), ZONES, cfg) == ()


def test_state_at_the_edge_of_a_big_zone_is_a_candidate(cfg: Config) -> None:
    """Just inside the MOA's east edge, far from its center."""
    state = make_state(lat=37.40, lon=-79.451)
    assert "LYNCHBURG-MOA" in candidate_zone_ids(state, ZONES, cfg)


def test_state_just_outside_a_boundary_is_still_a_candidate(cfg: Config) -> None:
    """~500 m east of P-901: the one-ring buffer keeps it for the buffered check."""
    state = make_state(lat=37.425, lon=-79.174)
    assert "P-901" in candidate_zone_ids(state, ZONES, cfg)


def test_zone_smaller_than_a_cell_is_not_lost(cfg: Config) -> None:
    """A ~20 m zone holds no cell centers; the overlap rule must still find it."""
    tiny = make_zone("TINY", -79.2501, 37.4001, -79.2499, 37.4003)
    state = make_state(lat=37.4002, lon=-79.2500)
    assert candidate_zone_ids(state, [tiny], cfg) == ("TINY",)


def test_keeps_zone_order(cfg: Config) -> None:
    """Overlapping zones come back in input order."""
    twin = make_zone("TWIN", -79.25, 37.40, -79.18, 37.45)
    state = make_state()
    assert candidate_zone_ids(state, [twin, P_901], cfg) == ("TWIN", "P-901")
    assert candidate_zone_ids(state, [P_901, twin], cfg) == ("P-901", "TWIN")


@pytest.mark.parametrize("resolution", [16, -1, "7", True, None, 7.0])
def test_rejects_bad_resolution(cfg: Config, resolution: Any) -> None:
    raw = {**cfg.raw, "geometry": {**cfg.raw["geometry"], "h3_resolution": resolution}}
    with pytest.raises(ValueError, match="h3_resolution"):
        candidate_zone_ids(make_state(), ZONES, Config(raw))


def test_rejects_missing_geometry_section(cfg: Config) -> None:
    raw = {k: v for k, v in cfg.raw.items() if k != "geometry"}
    with pytest.raises(ValueError, match="h3_resolution"):
        candidate_zone_ids(make_state(), ZONES, Config(raw))
