"""Stream C (part 1) tests - geo/zone_index.py H3 coarse filter."""
from __future__ import annotations

import math
from typing import Any

import pytest
from nfz_support import make_state
from shapely.geometry import box

from air.detectors.no_fly_zone.config import Config
from air.detectors.no_fly_zone.geo.containment import check_containment
from air.detectors.no_fly_zone.geo.zone_index import candidate_zone_ids
from air.detectors.no_fly_zone.types import Activation, AirspaceZone, Datum, ZoneType


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


# ---------------------------------------------------------------- NIC-scaled rings
# P-901's east edge is lon -79.18. At lat 37.425 one km is ~0.0113 deg of lon.
KM_LON = 1 / 88.4


def test_nic2_just_outside_a_zone_is_still_a_candidate(cfg: Config) -> None:
    """10 km east of P-901 is inside NIC 2's 14.8 km radius: keep the zone."""
    state = make_state(lat=37.425, lon=-79.18 + 10 * KM_LON, nic=2)
    assert "P-901" in candidate_zone_ids(state, ZONES, cfg)


def test_same_position_with_good_nic_is_not_a_candidate(cfg: Config) -> None:
    """The same spot at NIC 8 (185 m) is a confident clear: rings stay few."""
    state = make_state(lat=37.425, lon=-79.18 + 10 * KM_LON, nic=8)
    assert "P-901" not in candidate_zone_ids(state, ZONES, cfg)


def test_nic2_far_beyond_its_reach_is_not_a_candidate(cfg: Config) -> None:
    """60 km east is far past NIC 2's radius: the disk must not grow without bound.

    Rings are sized by the shortest cell edge, so the disk can overshoot the
    radius by up to ~2x in some directions; the exact check trims that.
    """
    state = make_state(lat=37.425, lon=-79.18 + 60 * KM_LON, nic=2)
    assert "P-901" not in candidate_zone_ids(state, ZONES, cfg)


def test_missing_nic_uses_the_configured_default(cfg: Config) -> None:
    """No NIC falls back to geometry.default_uncertainty_m, as containment does."""
    raw = {**cfg.raw, "geometry": {**cfg.raw["geometry"], "default_uncertainty_m": 15000}}
    state = make_state(lat=37.425, lon=-79.18 + 10 * KM_LON, nic=None)
    assert "P-901" not in candidate_zone_ids(state, ZONES, cfg)
    assert "P-901" in candidate_zone_ids(state, ZONES, Config(raw))


NIC_RADIUS_KM = {1: 37.04, 2: 14.816, 3: 7.408, 4: 3.704, 5: 1.852, 6: 1.1112,
                 7: 0.3704, 8: 0.1852, 9: 0.075, 10: 0.025, 11: 0.0075, None: 0.185}
KM_LAT = 1 / 111.0
DIAG = math.sqrt(0.5)
# Unit steps away from P-901 (west -79.25, south 37.40, east -79.18, north 37.45),
# from an edge midpoint or a corner: (lat, lon, d_lat, d_lon).
P901_PROBES = [
    (37.425, -79.18, 0, 1), (37.425, -79.25, 0, -1),
    (37.45, -79.215, 1, 0), (37.40, -79.215, -1, 0),
    (37.45, -79.18, DIAG, DIAG), (37.40, -79.25, -DIAG, -DIAG),
]


@pytest.mark.parametrize("nic", list(NIC_RADIUS_KM))
@pytest.mark.parametrize("fraction", [0.5, 0.9, 0.99])
def test_never_drops_a_zone_the_buffered_check_would_hit(
    cfg: Config, nic: int | None, fraction: float
) -> None:
    """Recall guarantee: every probe inside the uncertainty radius of P-901 is
    one containment's buffered test hits, so the pre-filter must offer it."""
    d_km = NIC_RADIUS_KM[nic] * fraction
    for lat, lon, d_lat, d_lon in P901_PROBES:
        state = make_state(
            lat=lat + d_km * d_lat * KM_LAT, lon=lon + d_km * d_lon * KM_LON, nic=nic
        )
        assert check_containment(state, [P_901], cfg).buffered_contained
        assert candidate_zone_ids(state, [P_901], cfg) == ("P-901",)
