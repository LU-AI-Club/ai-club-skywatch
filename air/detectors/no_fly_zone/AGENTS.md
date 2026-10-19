# NoFlyZoneDetector — instructions for AI coding agents

Read by any coding agent working in this folder (Codex, Cursor, Copilot, Gemini CLI,
Claude Code via the CLAUDE.md beside this file). People: README.md is your map;
these are the same rules, stated for an agent.

SkyWatch (LU AI Club, Fall 2026, with Xenith Solutions) air-domain detector for SENTINEL.
Air-domain adaptation of SENTINEL maritime detector M-005 Risk Zone Entry.
Full design: NoFlyZoneDetector_Design_and_Build_Plan.docx (ask the user for it if needed).

## Hard rules
- `types.py` and `config/` are LEAD-OWNED contracts. Do not change them unless the user
  explicitly asks. If a module seems to need a contract change, stop and say so.
- Every module imports only from `no_fly_zone.types` and `no_fly_zone.config`, never from
  another module. Duplicate small helpers rather than cross-import.
  Two documented exceptions, both LEAD-OWNED wiring, not logic: `logic/detector.py`
  imports the stages, and `emit.py` imports `contracts`. Keeping `contracts` out of
  every other module is exactly why `emit.py` exists.
- Pure functions: no file reads or network at import time, no globals. Config is passed
  in as `cfg`, never loaded inside a module.
- No constants inline. Tunable numbers go in `config/config.yaml`.
- Functions that can fail return a result object with a reason, never bare None.
- Type hints on every public signature. Must pass `mypy` and `ruff`.
- Use relative imports (`from ..types import ...`). A local `types.py` shadows the stdlib
  module; relative imports sidestep that wherever the package is rooted.

## Scope decisions (settled)
- Sampling: 1 Hz per aircraft from our own ADS-B receiver (dump1090/AirNav).
- Geography: KLYH (37.3267, -79.2004), 150 nm radius.
- Airspace: FAA Special Use Airspace GeoJSON + FAA TFR list. NOT UDDS (drone-only).
- Collector is a separate process writing hourly Parquet; the detector reads files only.
- Dashboard: Streamlit + Folium/pydeck reading detections.jsonl + Parquet states.

## Pipeline (each stage is one stream/module)
H3 coarse filter -> exact containment -> vertical check -> activation -> context signals -> score/emit.

Stream G builds the internal `types.Detection`. `emit.py` converts it to the vendored
`contracts.Detection` on the way out, and that is what `detections.jsonl` contains.
Stream G must populate `extras` with `observed_at`, `source_row_id`, `lat` and `lon`,
because the platform contract requires a timestamp and provenance that `types.Detection`
does not carry. See emit.py for the full field mapping.
Each stage records an ExitReason when a state leaves without a detection.

## Module map and signatures
| Stream | File | Signature |
|---|---|---|
| A | ingest/adsb_loader.py | load_states(path) -> Iterator[AircraftState] |
| B | ingest/airspace_loader.py | load_zones(path) -> list[AirspaceZone] |
| C | geo/zone_index.py | candidate_zone_ids(state, zones, cfg) -> tuple[str, ...] |
| C | geo/containment.py | check_containment(state, zones, cfg) -> ContainmentResult |
| D | geo/altitude.py | vertical_check(state, zone) -> VerticalResult |
| E | logic/activation.py | is_active(zone, ts) -> ActivationResult |
| F | logic/context.py | gather_signals(state, cfg) -> list[ContextSignal] |
| G | logic/scoring.py | build_detection(...) -> Detection |
| H | cli.py, fixtures/ | python -m air.detectors.no_fly_zone run --input x --out y |
| I | collect/collector.py | collect(url, out_dir) -> None |
| J | dashboard/app.py | streamlit run air/detectors/no_fly_zone/dashboard/app.py |
| Lead | logic/detector.py | wires stages only |
| Lead | emit.py | to_platform_detection(detection) -> contracts.Detection |

## Input data
`ingest/adsb_loader.py` reads JSON (AircraftState field names) or readsb/tar1090 CSV
such as `data/lynchburg_adsb.csv`. CSV columns used: h=icao hex, timestamp=UTC,
la/lo=lat/lon, ab=alt_baro ft, ag=alt_geom ft, gs=ground speed, tr=track, f=callsign,
sq=squawk, c=emitter category, n=NIC, np=NACp, og=on_ground. The loader's docstring is
the authority; `air/normalizers/COLUMN_MAP.md` documents every column in the file.

## Definition of done per module
Signature matches the table; docstring states inputs, outputs, and failure causes;
at least one firing and one non-firing test; mypy and ruff clean; no import-time I/O.
