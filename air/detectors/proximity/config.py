"""Proximity detector configuration — loads configs/detectors/proximity.yaml.

Thresholds are never hardcoded. Code asks ``cfg.max_tcpa_s``; the number lives
in the YAML. ``config_version`` travels with every Detection so a result from
six weeks ago can be explained by the exact rules that produced it.

OWNER: done (scaffold). Nobody needs to edit this to finish the MVP.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Mapping

import yaml

from contracts import SeverityLevel

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "detectors" / "proximity.yaml"
)


@dataclass(frozen=True, slots=True)
class SeverityTier:
    """One row of the severity table. Both limits must hold to match."""

    severity: SeverityLevel
    max_horizontal_nm: float
    max_vertical_ft: float

    def __post_init__(self) -> None:
        if isinstance(self.severity, str):
            object.__setattr__(self, "severity", SeverityLevel(self.severity.upper()))
        if self.max_horizontal_nm <= 0 or self.max_vertical_ft <= 0:
            raise ValueError("tier limits must be positive")


@dataclass(frozen=True, slots=True)
class ProximityConfig:
    detector_id: str = "skywatch.proximity"
    detector_version: str = "0.1.0"
    config_version: str = "unversioned"

    grid_step_s: float = 1.0
    max_gap_s: float = 30.0

    cell_size_deg: float = 0.5
    max_vertical_prefilter_ft: float = 2000.0
    ground_altitude_ft: float = 500.0
    ground_speed_kt: float = 50.0

    max_tcpa_s: float = 120.0

    tiers: tuple[SeverityTier, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.grid_step_s <= 0:
            raise ValueError("grid_step_s must be positive")
        if self.max_tcpa_s <= 0:
            raise ValueError("max_tcpa_s must be positive")
        tiers = tuple(
            t if isinstance(t, SeverityTier) else SeverityTier(**t) for t in self.tiers
        )
        object.__setattr__(self, "tiers", tiers)

    def to_parameters(self) -> dict[str, Any]:
        """Flat dict for the provenance record (what rules produced this?)."""
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name == "tiers":
                value = [
                    {
                        "severity": t.severity.value,
                        "max_horizontal_nm": t.max_horizontal_nm,
                        "max_vertical_ft": t.max_vertical_ft,
                    }
                    for t in value
                ]
            out[f.name] = value
        return out


def load_config(path: str | Path | None = None) -> ProximityConfig:
    """Read the YAML rule set into a frozen ``ProximityConfig``."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw: Mapping[str, Any] = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    known = {f.name for f in fields(ProximityConfig)}
    unknown = set(raw) - known
    if unknown:
        raise ValueError(f"unknown keys in {target.name}: {sorted(unknown)}")
    return ProximityConfig(**{k: raw[k] for k in raw})


__all__ = ["DEFAULT_CONFIG_PATH", "ProximityConfig", "SeverityTier", "load_config"]
