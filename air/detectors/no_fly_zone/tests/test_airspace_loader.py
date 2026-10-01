"""Stream B tests - ingest/airspace_loader.py."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ..ingest.airspace_loader import load_zones
from ..types import Activation, Datum, ZoneType
from .conftest import AIRSPACE_FILE


def test_parses_the_three_fixture_zones() -> None:
    """P-901, TFR-6/1234 and LYNCHBURG-MOA come back with their bands intact."""
    zones = {z.zone_id: z for z in load_zones(AIRSPACE_FILE)}
    assert set(zones) == {"P-901", "TFR-6/1234", "LYNCHBURG-MOA"}
    assert zones["P-901"].zone_type is ZoneType.PROHIBITED
    assert zones["P-901"].ceiling_ft == 18000.0
    assert zones["LYNCHBURG-MOA"].ceiling_datum is Datum.FL
    tfr = zones["TFR-6/1234"]
    assert tfr.activation is Activation.WINDOW
    assert len(tfr.active_windows) == 1


def test_rejects_a_file_that_is_not_a_featurecollection(tmp_path: Path) -> None:
    """Raises ValueError rather than returning an empty list - an empty zone set
    would silently make every aircraft look clean."""
    path = tmp_path / "bare.json"
    path.write_text(json.dumps({"type": "Feature"}))
    with pytest.raises(ValueError, match="FeatureCollection"):
        load_zones(path)
