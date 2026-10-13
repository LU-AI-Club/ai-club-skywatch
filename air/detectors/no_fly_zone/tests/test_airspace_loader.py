"""Stream B tests - ingest/airspace_loader.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from ..ingest.airspace_loader import load_zones
from ..logic.activation import is_active
from ..types import Activation, ActivationState, Datum, ZoneType
from .conftest import AIRSPACE_FILE

SKIP = pytest.mark.skip(reason="stream B: not implemented")



def test_parses_the_three_fixture_zones() -> None:
    """P-901, TFR-6/1234 and LYNCHBURG-MOA come back with their bands intact."""
    zones = {z.zone_id: z for z in load_zones(AIRSPACE_FILE)}
    assert set(zones) == {'P-901', 'TFR-6/1234', 'LYNCHBURG-MOA'}
    assert zones['P-901'].zone_type is ZoneType.PROHIBITED
    assert zones['P-901'].ceiling_ft == 18000.0
    tfr = zones['TFR-6/1234']
    assert tfr.activation is Activation.WINDOW
    assert len(tfr.active_windows) == 1


def test_rejects_a_file_that_is_not_a_featurecollection(tmp_path: Path) -> None:
    """Raises ValueError rather than returning an empty list - an empty zone set
    would silently make every aircraft look clean."""
    bad_file = tmp_path / "not_a_featurecollection.json"
    bad_file.write_text(json.dumps({"type": "FeatureCollectionn", "features": []}))

    with pytest.raises(ValueError):
        load_zones(bad_file)


def test_missing_altitude_defaults_to_surface_to_unlimited(tmp_path: Path) -> None:
    """A zone with no altitude band is kept, spanning surface to unlimited."""
    data = json.loads(Path(AIRSPACE_FILE).read_text(encoding="utf-8"))
    for key in ("floor_ft", "ceiling_ft", "floor_datum", "ceiling_datum"):
        data["features"][0]["properties"].pop(key, None)
    no_altitude = tmp_path / "no_altitude.json"
    no_altitude.write_text(json.dumps(data), encoding="utf-8")

    zone = load_zones(no_altitude)[0]

    assert zone.floor_ft == 0.0
    assert zone.floor_datum is Datum.SFC
    assert zone.ceiling_ft == float("inf")
    assert zone.ceiling_datum is Datum.MSL

def _write_variant(tmp_path: Path, name: str, edit: Any) -> Path:
    """Copy the fixture with its first feature edited by ``edit``."""
    data = json.loads(Path(AIRSPACE_FILE).read_text(encoding="utf-8"))
    edit(data["features"][0])
    out = tmp_path / f"{name}.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


def test_missing_ceiling_keeps_the_published_floor(tmp_path: Path) -> None:
    """Only the missing side defaults; the floor the source did publish stays."""
    def drop_ceiling(feature: dict[str, Any]) -> None:
        feature["properties"].update(floor_ft=2000, floor_datum="MSL")
        feature["properties"].pop("ceiling_ft")

    zone = load_zones(_write_variant(tmp_path, "no_ceiling", drop_ceiling))[0]

    assert (zone.floor_ft, zone.floor_datum) == (2000.0, Datum.MSL)
    assert (zone.ceiling_ft, zone.ceiling_datum) == (float("inf"), Datum.MSL)


def test_window_without_timezone_is_read_as_utc(tmp_path: Path) -> None:
    """A naive window must not crash is_active later; it is read as UTC."""
    tfr_path = _write_variant(tmp_path, "naive", lambda f: None)
    data = json.loads(tfr_path.read_text(encoding="utf-8"))
    for feature in data["features"]:
        for window in feature["properties"].get("active_windows", []):
            window["start"] = window["start"].replace("+00:00", "")
            window["end"] = window["end"].replace("+00:00", "").replace("Z", "")
    tfr_path.write_text(json.dumps(data), encoding="utf-8")

    tfr = {z.zone_id: z for z in load_zones(tfr_path)}["TFR-6/1234"]
    window = tfr.active_windows[0]

    assert window.start.tzinfo is not None and window.start.utcoffset() == timedelta(0)
    assert window.start == datetime(2026, 9, 22, 19, 0, tzinfo=UTC)
    state = is_active(tfr, datetime(2026, 9, 22, 20, 15, tzinfo=UTC)).state
    assert state is ActivationState.ACTIVE


def test_multipolygon_zone_loads(tmp_path: Path) -> None:
    """FAA airspace includes MultiPolygons; one must not stop the whole load."""
    def to_multi(feature: dict[str, Any]) -> None:
        feature["geometry"] = {
            "type": "MultiPolygon",
            "coordinates": [feature["geometry"]["coordinates"]],
        }

    zones = load_zones(_write_variant(tmp_path, "multi", to_multi))

    assert len(zones) == 3
    assert zones[0].geometry.geom_type == "MultiPolygon"


def test_point_geometry_is_still_rejected(tmp_path: Path) -> None:
    def to_point(feature: dict[str, Any]) -> None:
        feature["geometry"] = {"type": "Point", "coordinates": [-79.2, 37.3]}

    with pytest.raises(ValueError, match="Point"):
        load_zones(_write_variant(tmp_path, "point", to_point))
