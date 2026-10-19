"""NoFlyZoneDetector - SkyWatch air-domain restricted-airspace incursion detector.

Air-domain adaptation of SENTINEL maritime detector M-005 (Risk Zone Entry).

Layout (see AGENTS.md for the owner of each stream):

    types.py      LEAD-OWNED contracts. Do not edit without the lead.
    config.py     loads config/config.yaml into a frozen Config.
    ingest/       A adsb_loader     B airspace_loader
    geo/          C zone_index + containment      D altitude
    logic/        E activation  F context  G scoring  + episodes.py, detector.py (lead)
    collect/      I collector - separate process, the only networked module
    dashboard/    J Streamlit read-only view
    cli.py        H harness: python -m air.detectors.no_fly_zone run ...
    adapter.py    LEAD-OWNED: the pipeline behind the shared BaseDetector API
    fixtures/     hand-built tracks and airspace for tests

Nothing is imported at module level on purpose. Importing a stage must never
drag in shapely, h3 or streamlit for someone who only needs the types, so
``build_detector`` imports what it needs when it is called.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapter import NoFlyZoneDetector


def build_detector(
    config_path: str | Path | None = None,
    airspace_path: str | Path | None = None,
) -> NoFlyZoneDetector:
    """Build the detector the shared runner (``scripts/replay_csv.py``) calls.

    Zero arguments is the runner's call: the packaged ``config/config.yaml``
    and the airspace file it names. Pass either path to override, exactly like
    the CLI's ``--config`` and ``--airspace``. Config and zones are loaded once
    here, not per window.

    Failure causes: whatever ``load_config`` or ``load_zones`` raise for a bad
    file. The runner reports that and skips NFZ rather than crashing.
    """
    from .adapter import NoFlyZoneDetector, configured_airspace_path
    from .config import DEFAULT_PATH, load_config
    from .ingest.airspace_loader import load_zones

    cfg = load_config(config_path if config_path is not None else DEFAULT_PATH)
    zones_file = Path(airspace_path) if airspace_path is not None else configured_airspace_path(cfg)
    return NoFlyZoneDetector(cfg, load_zones(zones_file))


__all__ = ["build_detector"]
