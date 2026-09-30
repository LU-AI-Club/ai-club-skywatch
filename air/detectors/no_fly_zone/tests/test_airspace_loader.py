"""Stream B tests - ingest/airspace_loader.py.

One firing case, one non-firing case. Both are skipped until the stream
lands: delete the skip mark as you implement, and make it go green.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..ingest.airspace_loader import load_zones
from ..types import Activation, Datum, ZoneType
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
        