# NoFlyZoneDetector

SkyWatch (LU AI Club, Fall 2026, with Xenith Solutions) air-domain detector for
SENTINEL. Air-domain adaptation of maritime detector **M-005 Risk Zone Entry**:
it flags aircraft inside a restricted *volume* — a horizontal polygon plus an
altitude band — while that volume is live.

The full rules live in [AGENTS.md](AGENTS.md) (read by AI coding agents too). This file is the map.

## Setup

Every NFZ team member needs all three extras: the pipeline imports shapely and
h3 from any stage, and the dashboard needs streamlit. Python 3.11+, from the
repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev,nfz,nfz-dashboard]"
pytest tests/air/detectors/no_fly_zone tests/air/normalizers/test_nfz_adsb.py -q
```

| Group | Packages | Used by |
| --- | --- | --- |
| *(always)* | pyyaml | `config.py` |
| `dev` | pytest, ruff, mypy, types-PyYAML | the definition of done below |
| `nfz` | shapely, h3, pyarrow | streams B and C (polygons, H3 filter), Parquet |
| `nfz-dashboard` | streamlit, pandas, pyarrow | stream J |

`-e` installs the repo in editable mode, so your code changes take effect
without reinstalling. Re-activate the venv in every new terminal.

## Status

Every stage is built except the collector's `collect()` loop (stream I). The
pipeline runs end to end:

```
$ python -m air.detectors.no_fly_zone run \
    --input air/detectors/no_fly_zone/fixtures/tracks/klyh_mixed.json \
    --out out/

no_fly_zone: air/detectors/no_fly_zone/fixtures/tracks/klyh_mixed.json
  config                 ok    baseline=nfz-rules-0.1.0+sua-2026-08-07
  B airspace_loader      ok    3 zones
  A adsb_loader          ok    5 states
  C-G pipeline           ok    2 episodes
  output                 ok    out/detections.jsonl (2 detections)
```

It also runs in the club's shared runner, next to the Spoofing and Proximity
detectors, through `build_detector()` and `adapter.py`:

```bash
python scripts/replay_csv.py --detector no_fly_zone --out out/replay.jsonl
```

Both routes give identical detections on the full recorded hour, at any
window size: open incursion episodes carry over from one window to the next,
and the runner flushes the detector after the last window.

Exit codes: `0` everything ran, `1` some stage is still a stub, `2` a real
error (bad file, bad config). Alongside `detections.jsonl` the CLI writes
`exit_reasons.json`, counting why every other state dropped out.

**One detection per incursion, not per report.** An aircraft that sends 19
reports while inside a zone produces one *episode* detection carrying its start
and end time, duration, report count and peak score (`logic/episodes.py`). An
episode closes after 2 consecutive clear reports or 30 s of silence (both in
`config.yaml`). Add `--per-report` to get the raw per-report detections the
episodes are built from.

### On real data: `data/lynchburg_adsb.csv`

`--input` takes the club's readsb CSV directly (one hour, ~284k rows, 915
aircraft; runs in about 15 s):

```bash
python -m air.detectors.no_fly_zone run --input data/lynchburg_adsb.csv --out out/lynchburg
streamlit run air/detectors/no_fly_zone/dashboard/app.py
```

In the dashboard sidebar set the output folder to `out/lynchburg` and the
states file to `data/lynchburg_adsb.csv`. The airspace is still the fixture's
three **fake** zones, so expect detections only in P-901 (just north of KLYH):
2 episodes from 21 firing reports - PDT5877 crossing for 41 s at ~16,500 ft and
N90508 clipping the edge at ~3,100 ft.

## Layout

```
no_fly_zone/
├── types.py              LEAD-OWNED contracts. Do not edit without the lead.
├── adapter.py            LEAD-OWNED. Shared-runner entry: AdsbObservation -> pipeline
├── config.py             loads the config below into a frozen Config
├── ingest/
│   └── airspace_loader.py    B  load_zones(path) -> list[AirspaceZone]
├── geo/
│   ├── zone_index.py         C  candidate_zone_ids(state, zones, cfg)
│   ├── containment.py        C  check_containment(state, zones, cfg)
│   └── altitude.py           D  vertical_check(state, zone)
├── logic/
│   ├── activation.py         E  is_active(zone, ts)
│   ├── context.py            F  gather_signals(state, cfg)
│   ├── scoring.py            G  build_detection(...)
│   ├── episodes.py        LEAD  group_episodes(reports, cfg) — one detection per incursion
│   └── detector.py        LEAD  run(states, zones, cfg) — wiring only
├── collect/collector.py      I  collect(url, out_dir) — separate process
├── dashboard/app.py          J  Streamlit view (see Status for the command)
├── cli.py                    H  the harness (implemented)
├── emit.py                LEAD  types.Detection -> contracts.Detection (implemented)
└── fixtures/                    hand-built zones and tracks — see its README
```

Outside this folder, following the repo-wide layout in `docs/CONTRIBUTING.md`:

```
configs/detectors/no_fly_zone.yaml        LEAD-OWNED. Every tunable number lives here.
air/normalizers/no_fly_zone_adsb.py    A  load_states(path) -> Iterator[AircraftState]
tests/air/detectors/no_fly_zone/          one test_nfz_*.py file per stream
tests/air/normalizers/test_nfz_adsb.py    tests for stream A
```

## Pipeline

```
H3 coarse filter -> exact containment -> vertical check
                 -> activation -> context signals -> score
                 -> episode grouping -> emit
```

Each stage records an `ExitReason` when a state leaves without a detection, so
a quiet run can be explained instead of assumed broken.

## Working here

Three rules from AGENTS.md that catch people out:

1. **Stages never import each other.** Every module imports only from
   `..types` and `..config`. Duplicate a small helper rather than cross-import.
   That one-way rule is what lets each stream be owned and tested alone.
2. **Config is passed in as `cfg`.** No module opens `config.yaml` itself, and
   no tunable number is typed inline.
3. **Failures return a result object with a reason, never a bare `None`.**

Inside this package, use relative imports (`from ..types import ...`). A local
`types.py` shadows the stdlib module, and relative imports sidestep that
regardless of where the package is rooted. Code outside the package (the tests,
the ADS-B loader in `air/normalizers/`) uses the full path instead:
`from air.detectors.no_fly_zone.types import ...`.

## Definition of done, per stream

Signature matches the table above; docstring states inputs, outputs and failure
causes; at least one firing and one non-firing test; `ruff` and `mypy` clean;
no I/O at import time.

```bash
# one-time setup: see Setup above
pip install -e ".[dev,nfz,nfz-dashboard]"

pytest tests/air/detectors/no_fly_zone tests/air/normalizers/test_nfz_adsb.py -q
ruff check air/detectors/no_fly_zone/ air/normalizers/no_fly_zone_adsb.py tests/air/detectors/no_fly_zone/
mypy air/detectors/no_fly_zone/ air/normalizers/no_fly_zone_adsb.py tests/air/detectors/no_fly_zone/
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

`tests/air/detectors/no_fly_zone/test_nfz_emit.py` runs today and is the proof the shape is accepted by the
contract's own validation. Keep it green.

## Still open for the lead

AGENTS.md's signature table now matches the code, including `cfg` on
`check_containment` and `candidate_zone_ids`. Remaining: `types.py` uses
`class X(str, Enum)`, which ruff flags as `UP042` (suggesting `StrEnum`). It is
suppressed rather than changed — `str, Enum` keeps `ZoneType.TFR == "TFR"` true
for JSON round-tripping and `StrEnum` would change `str()` output. Your call.
