"""Guards the shared contracts. If this fails, nobody else's tests matter."""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import Any

import pytest

from air.detectors.no_fly_zone.config import load_config
from air.detectors.no_fly_zone.types import AircraftState, Detection, Severity


def _state(**kw: Any) -> AircraftState:
    base: dict[str, Any] = dict(
                icao24="ace81d", timestamp=datetime(2026, 9, 1, 0, 25, 40, tzinfo=timezone.utc),
                lat=37.33, lon=-79.20, alt_baro_ft=4850.0, alt_geom_ft=5200.0,
                ground_speed_kt=186.7, track_deg=4.9, callsign="AAL1715", squawk=None,
                emitter_category="A3", nic=8, nac_p=9, on_ground=False, source_row_id="row-1")
    base.update(kw)
    return AircraftState(**base)


def test_state_is_frozen() -> None:
    s = _state()
    with pytest.raises(FrozenInstanceError):
        # Assigning to a frozen field is the point of the test, so mypy's
        # (correct) complaint is silenced rather than avoided.
        s.lat = 0.0  # type: ignore[misc]


def test_config_loads_and_validates() -> None:
    cfg = load_config()
    assert cfg["sampling"]["target_hz"] == 1.0
    assert cfg.baseline_version.startswith("nfz-rules-0.1.0+sua-")


def test_detection_serializes_to_contract_shape() -> None:
    d = Detection("skywatch.no_fly_zone", "0.1.0", ("aircraft:ace81d",), "restricted_airspace_incursion",
                  Severity.HIGH, 0.82, 0.82, ("obs:1",), "air-features-v1", "nfz-rules-0.1.0+sua-2026-08-07",
                  ("fact",), ("limit",))
    out = d.to_dict()
    assert out["severity"] == "HIGH"
    assert isinstance(out["entity_ids"], list)
