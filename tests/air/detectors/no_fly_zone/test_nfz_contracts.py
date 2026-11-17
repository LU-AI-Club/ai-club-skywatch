"""Guards the shared contracts. If this fails, nobody else's tests matter."""
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from typing import Any

import pytest

from air.detectors.no_fly_zone.config import load_config
from air.detectors.no_fly_zone.types import AircraftState, Detection, Severity


def _state(**kw: Any) -> AircraftState:
    base: dict[str, Any] = dict(
                icao24="ace81d", timestamp=datetime(2026, 9, 1, 0, 25, 40, tzinfo=UTC),
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


def test_config_defaults_missing_include_types_to_all_zone_types(tmp_path: Any) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH
    from air.detectors.no_fly_zone.types import ZoneType

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    del raw["airspace"]["include_types"]
    config_path = tmp_path / "without_include_types.yaml"
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    cfg = load_config(config_path)
    assert "include_types" not in cfg["airspace"]
    assert {zone_type.value for zone_type in ZoneType} == set(raw["scoring"]["base_by_zone_type"])


def test_config_allows_empty_include_types(tmp_path: Any) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["airspace"]["include_types"] = []
    config_path = tmp_path / "empty_include_types.yaml"
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    assert load_config(config_path)["airspace"]["include_types"] == []


def test_config_rejects_duplicate_include_types(tmp_path: Any) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["airspace"]["include_types"] = ["MOA", "MOA"]
    config_path = tmp_path / "duplicate_include_types.yaml"
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate airspace.include_types value: 'MOA'"):
        load_config(config_path)


@pytest.mark.parametrize("include_types", [["MAO"], "MOA"])
def test_config_rejects_invalid_include_types(tmp_path: Any, include_types: Any) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["airspace"]["include_types"] = include_types
    config_path = tmp_path / "bad_include_types.yaml"
    config_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="airspace.include_types"):
        load_config(config_path)


def test_detection_serializes_to_contract_shape() -> None:
    d = Detection("skywatch.no_fly_zone", "0.1.0", ("icao24:ace81d",), "restricted_airspace_incursion",
                  Severity.HIGH, 0.82, 0.82, ("obs:1",), "air-features-v1", "nfz-rules-0.1.0+sua-2026-08-07",
                  ("fact",), ("limit",))
    out = d.to_dict()
    assert out["severity"] == "HIGH"
    assert isinstance(out["entity_ids"], list)



@pytest.mark.parametrize(
    ("section", "key", "value"),
    [("dedup", "clear_observations_to_close", 0),
     ("dedup", "clear_observations_to_close", True),
     ("sampling", "max_gap_sec", 0),
     ("sampling", "seen_retention_sec", 30)],  # must exceed max_gap_sec
)
def test_episode_settings_are_validated(tmp_path: Any, section: str, key: str, value: Any) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw[section][key] = value
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match=key):
        load_config(bad)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("persistence_min_factor", 0.0),
        ("persistence_min_factor", 1.1),
        ("persistence_saturation_sec", 0),
        ("buffered_position_factor", 0.6),
        ("active_activation_factor", float("nan")),
        ("unknown_activation_factor", float("inf")),
        ("strict_position_min_factor", True),
    ],
)
def test_confidence_settings_are_validated(
    tmp_path: Any, key: str, value: Any
) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    raw["scoring"]["confidence"][key] = value
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match=key):
        load_config(bad)


@pytest.mark.parametrize(
    "missing",
    ["confidence", "active_activation_factor"],
)
def test_missing_confidence_settings_are_rejected(tmp_path: Any, missing: str) -> None:
    import yaml

    from air.detectors.no_fly_zone.config import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    if missing == "confidence":
        del raw["scoring"]["confidence"]
    else:
        del raw["scoring"]["confidence"][missing]
    bad = tmp_path / "bad.yaml"
    bad.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError, match=missing):
        load_config(bad)
