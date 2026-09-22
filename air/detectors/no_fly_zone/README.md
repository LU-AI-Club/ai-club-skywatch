# NoFlyZoneDetector

SkyWatch (LU AI Club, Fall 2026, with Xenith Solutions) air-domain detector for
SENTINEL. Air-domain adaptation of maritime detector **M-005 Risk Zone Entry**:
it flags aircraft inside a restricted *volume* — a horizontal polygon plus an
altitude band — while that volume is live.

The full rules live in [CLAUDE.md](CLAUDE.md). This file is the map.

## Status

Scaffolded. Every stage is a stub raising `NotImplementedError` with a
docstring stating its inputs, outputs and failure causes. The harness, the
config loader, the contracts and the fixtures are real and working, so you can
run the whole pipeline today and watch your stage light up as you fill it in.

```
$ python -m air.detectors.no_fly_zone run \
    --input air/detectors/no_fly_zone/fixtures/tracks/klyh_mixed.json \
    --out out/

no_fly_zone: .../klyh_mixed.json
  config                 ok    baseline=nfz-rules-0.1.0+sua-2026-08-07
  B airspace_loader      TODO  stream B: airspace_loader
  A adsb_loader          TODO  stream A: adsb_loader
  C-G pipeline           TODO  lead: detector wiring
  output                 ok    out/detections.jsonl
```

Exit codes: `0` everything ran, `1` some stage is still a stub, `2` a real
error (bad file, bad config).

## Layout

```
no_fly_zone/
├── types.py              LEAD-OWNED contracts. Do not edit without the lead.
├── config.py             loads config/config.yaml into a frozen Config
├── config/config.yaml    LEAD-OWNED. Every tunable number lives here.
├── ingest/
│   ├── adsb_loader.py        A  load_states(path) -> Iterator[AircraftState]
│   └── airspace_loader.py    B  load_zones(path) -> list[AirspaceZone]
├── geo/
│   ├── zone_index.py         C  candidate_zone_ids(state, zones, cfg)
│   ├── containment.py        C  check_containment(state, zones, cfg)
│   └── altitude.py           D  vertical_check(state, zone)
├── logic/
│   ├── activation.py         E  is_active(zone, ts)
│   ├── context.py            F  gather_signals(state, cfg)
│   ├── scoring.py            G  build_detection(...)
│   └── detector.py        LEAD  run(states, zones, cfg) — wiring only
├── collect/collector.py      I  collect(url, out_dir) — separate process
├── dashboard/app.py          J  streamlit run dashboard/app.py
├── cli.py                    H  the harness (implemented)
├── emit.py                LEAD  types.Detection -> contracts.Detection (implemented)
├── fixtures/                    hand-built zones and tracks — see its README
└── tests/                       one file per stream, two tests each
```

## Pipeline

```
H3 coarse filter -> exact containment -> vertical check
                 -> activation -> context signals -> score/emit
```

Each stage records an `ExitReason` when a state leaves without a detection, so
a quiet run can be explained instead of assumed broken.

## Working here

Three rules from CLAUDE.md that catch people out:

1. **Stages never import each other.** Every module imports only from
   `..types` and `..config`. Duplicate a small helper rather than cross-import.
   That one-way rule is what lets each stream be owned and tested alone.
2. **Config is passed in as `cfg`.** No module opens `config.yaml` itself, and
   no tunable number is typed inline.
3. **Failures return a result object with a reason, never a bare `None`.**

Use relative imports (`from ..types import ...`). A local `types.py` shadows
the stdlib module, and relative imports sidestep that regardless of where the
package is rooted.

## Definition of done, per stream

Signature matches the table above; docstring states inputs, outputs and failure
causes; at least one firing and one non-firing test; `ruff` and `mypy` clean;
no I/O at import time.

```bash
# one-time setup - this is all most people need
pip install -e ".[dev]"

# streams B and C only, once you start using shapely/h3
pip install -e ".[nfz]"

pytest air/detectors/no_fly_zone/tests -q
ruff check air/detectors/no_fly_zone/
mypy air/detectors/no_fly_zone/
```

Delete the `@SKIP` mark on your two tests as you implement.

## Output contract — decided

`detections.jsonl` contains the **platform** contract,
[`contracts.Detection`](../../../contracts/detection.py). `contracts/__init__.py`
states that emitting the real one keeps Week-11 TCE/CAATS integration "a wiring
exercise instead of a rewrite", so that is what we emit.

The stages still build the internal `types.Detection`, and
[`emit.py`](emit.py) converts at the boundary. That keeps two rules intact:
`types.py` is untouched, and no stage module imports `contracts`.

Two things to know:

- **`anomaly_score` has no first-class home.** The platform contract has one
  probability field, `confidence`, meaning "how sure are we". Our
  `anomaly_score` means "how anomalous is this" — a different quantity.
  Collapsing them would be wrong, so `confidence` carries
  `raw_model_confidence` and `anomaly_score` rides in
  `metadata["anomaly_score"]`. Revisit if the platform grows a score field.
- **Stream G must populate `extras`.** The platform requires `temporal_bounds`
  and `provenance`; `types.Detection` carries neither. So `extras` must hold
  `observed_at`, `source_row_id`, `lat` and `lon`, plus `altitude_ft`,
  `zone_id` and `penetration_nm` when known. Missing keys raise a `ValueError`
  naming the key — emitting a detection with a fabricated timestamp would be
  worse than emitting none.

`tests/test_emit.py` runs today and is the proof the shape is accepted by the
contract's own validation. Keep it green.

## Still open for the lead

CLAUDE.md's signature table now matches the code, including `cfg` on
`check_containment` and `candidate_zone_ids`. Remaining: `types.py` uses
`class X(str, Enum)`, which ruff flags as `UP042` (suggesting `StrEnum`). It is
suppressed rather than changed — `str, Enum` keeps `ZoneType.TFR == "TFR"` true
for JSON round-tripping and `StrEnum` would change `str()` output. Your call.
