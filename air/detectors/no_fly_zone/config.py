"""Loads configs/detectors/no_fly_zone.yaml once and hands out a frozen, validated object.

Modules receive `cfg` as a function argument; they never read the file
themselves. That keeps every function pure and every test able to pass
its own config.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from .types import Severity, ZoneType

# Repo-root configs/, like every other detector (configs/detectors/README.md).
DEFAULT_PATH = Path(__file__).resolve().parents[3] / "configs" / "detectors" / "no_fly_zone.yaml"


@dataclass(frozen=True)
class Config:
    raw: Mapping[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    @property
    def baseline_version(self) -> str:
        """Pins rule version AND airspace cycle, per the output contract."""
        return f"{self.raw['detector']['rules_version']}+sua-{self.raw['airspace']['source_asof']}"


def load_config(path: str | Path = DEFAULT_PATH) -> Config:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    _validate(raw)
    return Config(raw)


def _validate(raw: Mapping[str, Any]) -> None:
    for section in ("detector", "scope", "sampling", "airspace", "geometry", "scoring", "severity", "dedup"):
        if section not in raw:
            raise ValueError(f"config missing section: {section}")
    bases = raw["scoring"]["base_by_zone_type"]
    missing = {z.value for z in ZoneType} - set(bases)
    if missing:
        raise ValueError(f"scoring.base_by_zone_type missing: {sorted(missing)}")
    for z, v in bases.items():
        if not 0.0 <= float(v) <= 1.0:
            raise ValueError(f"base score for {z} out of range: {v}")
    for key in ("unknown_activation_cap", "buffered_only"):
        Severity(raw["severity"][key])  # raises if not a valid severity
    if raw["sampling"]["target_hz"] <= 0:
        raise ValueError("sampling.target_hz must be positive")
    if float(raw["sampling"]["max_gap_sec"]) <= 0:
        raise ValueError("sampling.max_gap_sec must be positive")
    clears = raw["dedup"]["clear_observations_to_close"]
    if isinstance(clears, bool) or not isinstance(clears, int) or clears < 1:
        raise ValueError("dedup.clear_observations_to_close must be an integer >= 1")
