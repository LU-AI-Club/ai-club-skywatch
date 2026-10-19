"""ADS-B spoofing / position-inconsistency detector.

Flags reports that cannot be true: movement that breaks physics, or an
aircraft that is not who it claims to be. It reports a deviation and the
evidence behind it, never intent -- TCE/CAATS owns Trust.

    from air.detectors.spoofing import build_detector

    detector = build_detector()
    detections = detector.detect_observations(observations)

``build_detector`` is what ``scripts/replay_csv.py`` looks for, so the
detector appears in the replay with no change to the runner.
"""

from __future__ import annotations

from pathlib import Path

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.detector import SpoofingDetector

# Sample reference data, committed with the fixtures. The identity branch's
# registry check needs an aircraft registry and the ICAO country blocks; the
# full datasets are too large for the repo, so these samples stand in until a
# caller supplies the real ones.
_REFERENCE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "spoofing"
_REGISTRY_CSV = _REFERENCE_DIR / "faa_registry_sample.csv"
_ICAO_BLOCKS_CSV = _REFERENCE_DIR / "icao_blocks_sample.csv"


def build_detector(config: SpoofingConfig | None = None) -> SpoofingDetector:
    """Construct the detector with its reference data, if that data is present.

    Zero-arg by design, because the replay runner calls it with no arguments.

    Missing reference files are not an error: the registry check simply does
    not run, and every other rule is unaffected. That keeps the detector
    usable on a machine that has not downloaded the registry.
    """
    registry = None
    icao_blocks = None

    if _REGISTRY_CSV.exists() and _ICAO_BLOCKS_CSV.exists():
        # Imported here so a malformed or missing reference file can never
        # stop the package from importing.
        from air.detectors.spoofing.reference import (
            load_faa_registry,
            load_icao_blocks,
        )

        try:
            registry = load_faa_registry(_REGISTRY_CSV)
            icao_blocks = load_icao_blocks(_ICAO_BLOCKS_CSV)
        except Exception:
            registry = None
            icao_blocks = None

    return SpoofingDetector(
        config=config or SpoofingConfig(),
        registry=registry,
        icao_blocks=icao_blocks,
    )


__all__ = ["build_detector", "SpoofingDetector", "SpoofingConfig"]
