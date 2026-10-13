"""NoFlyZoneDetector - SkyWatch air-domain restricted-airspace incursion detector.

Air-domain adaptation of SENTINEL maritime detector M-005 (Risk Zone Entry).

Layout (see CLAUDE.md for the owner of each stream):

    types.py      LEAD-OWNED contracts. Do not edit without the lead.
    config.py     loads config/config.yaml into a frozen Config.
    ingest/       A adsb_loader     B airspace_loader
    geo/          C zone_index + containment      D altitude
    logic/        E activation  F context  G scoring  + detector.py (lead)
    collect/      I collector - separate process, the only networked module
    dashboard/    J Streamlit read-only view
    cli.py        H harness: python -m air.detectors.no_fly_zone run ...
    fixtures/     hand-built tracks and airspace for tests

Nothing is imported here on purpose. Importing a stage must never drag in
shapely, h3 or streamlit for someone who only needs the types.
"""
