"""Config loads from YAML and nothing is hardcoded. OWNER: done (scaffold)."""

from __future__ import annotations

from air.detectors.proximity import ProximityConfig, load_config
from contracts import SeverityLevel


def test_default_config_loads():
    cfg = load_config()
    assert cfg.detector_id == "skywatch.proximity"
    assert cfg.config_version != "unversioned"


def test_tiers_are_ordered_tightest_first():
    cfg = load_config()
    assert [t.severity for t in cfg.tiers] == [
        SeverityLevel.HIGH,
        SeverityLevel.MEDIUM,
        SeverityLevel.LOW,
        SeverityLevel.INFO,
    ]
    horizontals = [t.max_horizontal_nm for t in cfg.tiers]
    assert horizontals == sorted(horizontals)


def test_parameters_are_serialisable_for_provenance():
    params = load_config().to_parameters()
    assert params["max_tcpa_s"] == 120.0
    assert params["tiers"][0]["severity"] == "HIGH"


def test_config_rejects_nonsense():
    import pytest

    with pytest.raises(ValueError):
        ProximityConfig(max_tcpa_s=0)
