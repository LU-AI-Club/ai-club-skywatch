"""Stream C tests - geo/zone_index.py + geo/containment.py."""
from __future__ import annotations

from ..config import Config
from ..geo.containment import check_containment
from ..geo.zone_index import candidate_zone_ids
from ..ingest.airspace_loader import load_zones
from ..types import ExitReason
from .conftest import AIRSPACE_FILE, make_state


def test_flags_a_state_inside_the_polygon(cfg: Config) -> None:
    """The default state sits inside P-901, so contained is True and penetration
    is a real distance."""
    zones = load_zones(AIRSPACE_FILE)
    state = make_state()
    ids = candidate_zone_ids(state, zones, cfg)
    assert "P-901" in ids
    result = check_containment(state, [z for z in zones if z.zone_id in ids], cfg)
    assert result.contained is True
    assert "P-901" in result.zone_ids
    assert result.penetration_nm is not None and result.penetration_nm > 0


def test_reports_outside_polygon_when_clear(cfg: Config) -> None:
    """A state east of KLYH hits nothing, and the result carries a reason rather
    than returning None."""
    zones = load_zones(AIRSPACE_FILE)
    result = check_containment(make_state(lat=37.10, lon=-78.80), zones, cfg)
    assert result.contained is False
    assert result.buffered_contained is False
    assert result.reason is ExitReason.OUTSIDE_POLYGON


def test_an_empty_candidate_list_is_no_candidate(cfg: Config) -> None:
    assert check_containment(make_state(), [], cfg).reason is ExitReason.NO_CANDIDATE


def test_just_outside_with_poor_nic_is_buffered_only(cfg: Config) -> None:
    """Outside the fence but within the NIC radius is buffered, not strict."""
    p901 = next(z for z in load_zones(AIRSPACE_FILE) if z.zone_id == "P-901")
    min_lon, min_lat, max_lon, max_lat = p901.geometry.bounds
    # ~300 m north of the top edge; NIC 6 means a 1.1 km containment radius.
    state = make_state(lat=max_lat + 0.0027, lon=(min_lon + max_lon) / 2, nic=6)
    assert "P-901" in candidate_zone_ids(state, [p901], cfg)
    result = check_containment(state, [p901], cfg)
    assert result.contained is False
    assert result.buffered_contained is True
