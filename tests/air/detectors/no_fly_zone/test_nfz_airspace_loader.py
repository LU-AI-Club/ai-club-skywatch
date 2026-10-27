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
from nfz_support import AIRSPACE_FILE, FIXTURES

from air.detectors.no_fly_zone.ingest.airspace_loader import load_zones
from air.detectors.no_fly_zone.logic.activation import is_active
from air.detectors.no_fly_zone.types import (
    Activation,
    ActivationState,
    AirspaceZone,
    Datum,
    ZoneType,
)

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


# --- real FAA data -----------------------------------------------------------
# klyh-faa-sample.geojson is nine real features from the FAA Special Use
# Airspace service, cut from the 52 within 150 nm of KLYH by
# scripts/make_faa_airspace.py. Chosen to cover every code path the fake
# fixtures never exercised: all four TYPE_CODEs, all three activation kinds,
# and the AGL / SFC / MSL / FL datums. The full file is generated, not
# committed - see .gitignore.
FAA_SAMPLE = FIXTURES / "airspace" / "klyh-faa-sample.geojson"


def _faa_zones() -> dict[str, AirspaceZone]:
    return {z.zone_id: z for z in load_zones(FAA_SAMPLE)}


def test_faa_sample_loads_every_feature() -> None:
    zones = _faa_zones()
    assert len(zones) == 9
    assert {z.zone_type for z in zones.values()} == {
        ZoneType.PROHIBITED,
        ZoneType.RESTRICTED,
        ZoneType.MOA,
        ZoneType.ALERT,
    }


def test_faa_repeated_names_get_distinct_ids() -> None:
    """The FAA reuses NAME across sub-areas with different altitude bands.

    logic/detector.py keys zones by id, so colliding ids would silently drop
    every duplicate but one - three of Farmville MOA, in this sample.
    """
    zones = _faa_zones()
    farmville = sorted(z for z in zones if z.startswith("FARMVILLE"))
    assert farmville == ["FARMVILLE MOA", "FARMVILLE MOA #2", "FARMVILLE MOA #3"]
    assert len(zones) == len(set(zones))


def test_faa_nonzero_sfc_floor_is_agl_not_the_surface() -> None:
    """A non-zero SFC value is a height above ground, not the surface.

    Reading it as SFC/0 would put the floor on the deck and flag aircraft
    legally overflying at 400 ft. AGL is honest, and geo/altitude.py then
    abstains for want of a terrain model.
    """
    farmville = _faa_zones()["FARMVILLE MOA"]
    assert (farmville.floor_ft, farmville.floor_datum) == (300.0, Datum.AGL)
    assert farmville.ceiling_datum is Datum.MSL


def test_faa_zero_sfc_floor_is_the_surface() -> None:
    """Only a zero value is literally the surface, and that stays SFC."""
    restricted = _faa_zones()["R-6602A"]
    assert (restricted.floor_ft, restricted.floor_datum) == (0.0, Datum.SFC)


def test_faa_flight_level_ceiling_converts_to_feet() -> None:
    """FL180 arrives as "180 FL STD"; types.py stores flight levels in feet."""
    evers = _faa_zones()["EVERS CENTER MOA"]
    assert (evers.ceiling_ft, evers.ceiling_datum) == (18000.0, Datum.FL)
    assert (evers.floor_ft, evers.floor_datum) == (11000.0, Datum.MSL)


def test_faa_activation_comes_from_the_times_of_use_prose() -> None:
    """CONTINUOUS is the only unambiguous value; the rest must not read ACTIVE.

    A schedule we cannot parse into windows is SCHEDULED with no windows, which
    logic/activation.py reports as UNKNOWN rather than guessing. Parsing
    "0800 - 1700, MON - FRI" into real windows is a separate piece of work.
    """
    zones = _faa_zones()
    assert zones["P-56"].activation is Activation.ALWAYS      # "CONTINUOUS"
    assert zones["R-6602A"].activation is Activation.NOTAM    # "...BY NOTAM"
    assert zones["FARMVILLE MOA"].activation is Activation.SCHEDULED
    assert zones["FARMVILLE MOA"].active_windows == ()

    live = is_active(zones["FARMVILLE MOA"], datetime(2026, 9, 22, 20, 15, tzinfo=UTC))
    assert live.state is ActivationState.UNKNOWN


def test_faa_sample_pins_the_publication_cycle() -> None:
    """source_asof must match the FAA cycle: Config.baseline_version stamps it
    onto every detection, so a stale value mislabels every result."""
    assert all(z.source == "faa_sua" for z in _faa_zones().values())
    assert {str(z.source_asof) for z in _faa_zones().values()} == {"2026-09-28"}
