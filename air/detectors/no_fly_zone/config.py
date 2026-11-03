"""Loads config/config.yaml once and hands out a frozen, validated object.

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

DEFAULT_PATH = Path(__file__).parent / "config" / "config.yaml"
_SQUAWK_GROUPS = frozenset({"unlawful_interference", "emergency", "non_discrete"})


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
    for section in (
        "detector", "scope", "sampling", "airspace", "squawks", "callsigns",
        "geometry", "scoring", "severity", "dedup",
    ):
        if section not in raw:
            raise ValueError(f"config missing section: {section}")
    _validate_context_lists(raw)
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


def _validate_context_lists(raw: Mapping[str, Any]) -> None:
    """Validate squawk categories and configured lifeguard callsign prefixes."""
    squawks = raw["squawks"]
    if not isinstance(squawks, Mapping) or set(squawks) != _SQUAWK_GROUPS:
        raise ValueError(f"squawks must define exactly these groups: {sorted(_SQUAWK_GROUPS)}")

    assigned_codes: dict[str, str] = {}
    for group, codes in squawks.items():
        if not isinstance(codes, list):
            raise ValueError(f"squawks.{group} must be a list")
        for code in codes:
            if (
                not isinstance(code, str)
                or len(code) != 4
                or any(digit not in "01234567" for digit in code)
            ):
                raise ValueError(f"squawks.{group} entries must be four-digit octal strings")
        if len(codes) != len(set(codes)):
            raise ValueError(f"squawks.{group} must not contain duplicates")
        for code in codes:
            if code in assigned_codes:
                raise ValueError(
                    f"squawk {code} cannot be in both {assigned_codes[code]} and {group}"
                )
            assigned_codes[code] = group

    callsigns = raw["callsigns"]
    prefixes = callsigns.get("lifeguard_prefixes") if isinstance(callsigns, Mapping) else None
    if not isinstance(prefixes, list):
        raise ValueError("callsigns.lifeguard_prefixes must be a list")
    if any(not isinstance(prefix, str) or not prefix.strip() for prefix in prefixes):
        raise ValueError("callsigns.lifeguard_prefixes entries must be non-empty strings")
    normalized_prefixes = [prefix.strip().upper() for prefix in prefixes]
    if len(normalized_prefixes) != len(set(normalized_prefixes)):
        raise ValueError("callsigns.lifeguard_prefixes must not contain duplicates")
