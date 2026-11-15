"""NoFlyZoneDetector - SkyWatch air-domain restricted-airspace incursion detector.

Air-domain adaptation of SENTINEL maritime detector M-005 (Risk Zone Entry).

Layout (see AGENTS.md for the owner of each stream):

    types.py      LEAD-OWNED contracts. Do not edit without the lead.
    config.py     loads configs/detectors/no_fly_zone.yaml into a frozen Config.
    ingest/       B airspace_loader  (A, the ADS-B loader, is air/normalizers/no_fly_zone_adsb.py)
    geo/          C zone_index + containment      D altitude
    logic/        E activation  F context  G scoring  + episodes.py, detector.py (lead)
    collect/      I collector - separate process, the only networked module
    dashboard/    J Streamlit read-only view
    cli.py        H harness: python -m air.detectors.no_fly_zone run ...
    adapter.py    LEAD-OWNED: the pipeline behind the shared BaseDetector API
    fixtures/     hand-built tracks and airspace (tests: tests/air/detectors/no_fly_zone/)

Nothing is imported at module level on purpose. Importing a stage must never
drag in shapely, h3 or streamlit for someone who only needs the types, so
``build_detector`` imports what it needs when it is called.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .adapter import NoFlyZoneDetector
    from .config import Config

_log = logging.getLogger(__name__)


DEMO_ZONES_ENV = "SKYWATCH_NFZ_DEMO_ZONES"
_TRUE = frozenset({"1", "true", "yes", "on"})


def demo_zones_requested() -> bool:
    """True when ``SKYWATCH_NFZ_DEMO_ZONES`` asks for the synthetic demo zones."""
    return os.environ.get(DEMO_ZONES_ENV, "").strip().lower() in _TRUE


def _build_detector(
    cfg: Config,
    airspace_path: str | Path,
    *,
    emit_open: bool,
    extra_airspace_paths: tuple[Path, ...] = (),
) -> NoFlyZoneDetector:
    from .adapter import NoFlyZoneDetector
    from .ingest.airspace_loader import load_filtered_zones

    zones = load_filtered_zones(airspace_path, cfg)
    for extra in extra_airspace_paths:
        added = load_filtered_zones(extra, cfg)
        # The zone index keys zones by id, so a clash would silently hide one.
        clash = {z.zone_id for z in zones} & {z.zone_id for z in added}
        if clash:
            raise ValueError(f"zone ids in {extra} clash with {airspace_path}: {sorted(clash)}")
        zones = zones + added
    return NoFlyZoneDetector(cfg, zones, emit_open=emit_open)


def build_detector(
    config_path: str | Path | None = None,
    airspace_path: str | Path | None = None,
    *,
    emit_open: bool = False,
) -> NoFlyZoneDetector:
    """Build the detector the shared runner (``scripts/replay_csv.py``) calls.

    Zero arguments is the runner's call: ``configs/detectors/no_fly_zone.yaml``
    and the airspace file it names. Pass either path to override, exactly like
    the CLI's ``--config`` and ``--airspace``. Config and zones are loaded once
    here, not per window. ``emit_open`` turns on live mode (see
    :func:`build_live_detector`).

    Failure causes: whatever ``load_config`` or ``load_zones`` raise for a bad
    file. The runner reports that and skips NFZ rather than crashing.
    """
    from .adapter import configured_airspace_path
    from .config import DEFAULT_PATH, load_config

    cfg = load_config(config_path if config_path is not None else DEFAULT_PATH)
    zones_file = Path(airspace_path) if airspace_path is not None else configured_airspace_path(cfg)
    return _build_detector(cfg, zones_file, emit_open=emit_open)


def build_live_detector(
    config_path: str | Path | None = None,
    airspace_path: str | Path | None = None,
    *,
    demo_zones: bool | None = None,
) -> NoFlyZoneDetector:
    """Build the detector for the live runner (``scripts/run_live_detector.py``).

    Same as :func:`build_detector`, with open episodes emitted every window
    (``episode_status == "OPEN"``, no end time) so an incursion reaches the
    detection table on entry and is updated in place until it closes. Replay
    and the CLI keep using :func:`build_detector`, which only emits finished
    episodes.

    Zones: the real FAA file at ``airspace.live_path`` when it exists (NFZ-12C),
    otherwise ``airspace.fixture_path`` with a WARNING in the runner's log, so a
    machine that has not generated the file still runs, visibly on test zones.
    An explicit ``airspace_path`` always wins.

    Demo zones: with ``demo_zones=True``, or when it is None and
    ``SKYWATCH_NFZ_DEMO_ZONES=1`` is set, the SYNTHETIC zones at
    ``airspace.demo_path`` are added on top of the zones above, with a WARNING in
    the log. They are not real airspace; they exist so a demo or a frontend test
    sees HIGH incursions on real local traffic. Off by default, and only the live
    builder reads them: replay, tests and the CLI never do.
    """
    from .adapter import configured_airspace_path, demo_airspace_path, live_airspace_path
    from .config import DEFAULT_PATH, load_config

    cfg = load_config(config_path if config_path is not None else DEFAULT_PATH)
    if airspace_path is None:
        live = live_airspace_path(cfg)
        if live is not None and live.is_file():
            airspace_path = live
        else:
            airspace_path = configured_airspace_path(cfg)
            _log.warning(
                "NFZ live: real FAA airspace not found at %s; using TEST zones from %s. "
                "Generate it with scripts/make_faa_airspace.py (docs/RUN_PIPELINE.md).",
                live, airspace_path,
            )
    extras: tuple[Path, ...] = ()
    if demo_zones if demo_zones is not None else demo_zones_requested():
        demo = demo_airspace_path(cfg)
        if demo is None:
            raise ValueError("demo zones requested but airspace.demo_path is not configured")
        extras = (demo,)
    detector = _build_detector(cfg, airspace_path, emit_open=True, extra_airspace_paths=extras)
    _log.info("NFZ live: %d zones loaded from %s", len(detector.zones), airspace_path)
    if extras:
        demo_ids = sorted(z.zone_id for z in detector.zones if z.source == "demo")
        _log.warning(
            "NFZ live: DEMO zones ON (%s from %s). These are NOT real airspace; "
            "unset %s to turn them off.",
            ", ".join(demo_ids), extras[0], DEMO_ZONES_ENV,
        )
    return detector


__all__ = ["DEMO_ZONES_ENV", "build_detector", "build_live_detector", "demo_zones_requested"]
