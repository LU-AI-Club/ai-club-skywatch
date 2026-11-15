"""Stream C (part 1) tests - geo/zone_index.py H3 coarse filter."""
from __future__ import annotations

from typing import Any

import pytest
from nfz_support import make_state
from shapely.geometry import box

from air.detectors.no_fly_zone.config import Config
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


def test_zone_cells_are_cached_per_geometry_and_dropped_when_it_is_freed() -> None:
    # The cache is keyed on the geometry object, not its serialized outline
    # (serializing every zone on every report was 85% of run time). An entry
    # must leave with its geometry so a reused id never gets another zone's cells.
    import gc

    from air.detectors.no_fly_zone.geo import zone_index

    zone = make_zone("TEMP", -79.3, 37.3, -79.1, 37.5)
    first = zone_index._zone_cells(zone, 7)
    assert zone_index._zone_cells(zone, 7) is first          # served from the cache
    key = (id(zone.geometry), 7)
    assert key in zone_index._CELLS_BY_GEOMETRY

    del zone, first
    gc.collect()
    assert key not in zone_index._CELLS_BY_GEOMETRY


def test_different_geometries_never_share_cells() -> None:
    from air.detectors.no_fly_zone.geo import zone_index

    near = make_zone("NEAR", -79.3, 37.3, -79.1, 37.5)
    far = make_zone("FAR", -76.2, 38.0, -76.0, 38.2)
    assert not zone_index._zone_cells(near, 7) & zone_index._zone_cells(far, 7)


# ---------------------------------------------------------------- inverted index

def _brute_force(state: Any, zones: list[AirspaceZone], res: int) -> tuple[str, ...]:
    """The pre-index algorithm: test every zone's cells against the plane's disk."""
    import h3

    from air.detectors.no_fly_zone.geo import zone_index

    nearby = set(h3.grid_disk(h3.latlng_to_cell(state.lat, state.lon, res), 1))
    return tuple(z.zone_id for z in zones if nearby & zone_index._zone_cells(z, res))


def test_index_matches_checking_every_zone_on_the_real_faa_zones(cfg: Config) -> None:
    """Parity on the committed live zones over a grid of positions, inside and out."""
    from air.detectors.no_fly_zone.adapter import live_airspace_path
    from air.detectors.no_fly_zone.ingest.airspace_loader import load_zones

    path = live_airspace_path(cfg)
    assert path is not None
    zones = load_zones(path)
    res = cfg.raw["geometry"]["h3_resolution"]
    checked = hits = 0
    for i in range(41):
        for j in range(41):
            state = make_state(lat=36.3 + i * 0.05, lon=-80.3 + j * 0.05)
            got = candidate_zone_ids(state, zones, cfg)
            assert got == _brute_force(state, zones, res)
            checked += 1
            hits += bool(got)
    assert hits > 50 and hits < checked      # the grid covers zones and open sky


def test_zone_cells_are_not_recomputed_per_report(
    cfg: Config, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of the index: per-report cost does not grow with the zone count."""
    from air.detectors.no_fly_zone.geo import zone_index

    zones = [
        make_zone(f"Z{i}", -79.9 + i * 0.01, 37.0, -79.89 + i * 0.01, 37.01) for i in range(200)
    ]
    candidate_zone_ids(make_state(), zones, cfg)          # builds the index once
    calls = 0
    real = zone_index._zone_cells

    def counting(zone: AirspaceZone, res: int) -> frozenset[str]:
        nonlocal calls
        calls += 1
        return real(zone, res)

    monkeypatch.setattr(zone_index, "_zone_cells", counting)
    for k in range(50):
        candidate_zone_ids(make_state(lat=37.005, lon=-79.895 + k * 0.01), zones, cfg)
    assert calls == 0


def test_a_new_zone_list_gets_a_new_index(cfg: Config) -> None:
    state = make_state()
    assert candidate_zone_ids(state, [TFR], cfg) == ()
    assert candidate_zone_ids(state, [TFR, P_901], cfg) == ("P-901",)


def test_appending_to_the_same_list_is_noticed(cfg: Config) -> None:
    """Callers should not edit a zone list in place, but if one does, no zone is lost."""
    zones = [TFR]
    state = make_state()
    assert candidate_zone_ids(state, zones, cfg) == ()
    zones.append(P_901)
    assert candidate_zone_ids(state, zones, cfg) == ("P-901",)


def test_index_cache_is_bounded(cfg: Config) -> None:
    from air.detectors.no_fly_zone.geo import zone_index

    for _ in range(3 * zone_index._INDEX_CACHE_SIZE):
        candidate_zone_ids(make_state(), list(ZONES), cfg)
    assert len(zone_index._INDEXES) <= zone_index._INDEX_CACHE_SIZE
