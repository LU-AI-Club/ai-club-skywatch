# NoFlyZoneDetector

SkyWatch (LU AI Club, Fall 2026, with Xenith Solutions) air-domain detector for
SENTINEL. Air-domain adaptation of maritime detector **M-005 Risk Zone Entry**:
it flags aircraft inside a restricted *volume* — a horizontal polygon plus an
altitude band — while that volume is live.

The full rules live in [CLAUDE.md](CLAUDE.md). This file is the map.

## Status

Streams A-G and the lead wiring are implemented and tested; the collector (I)
and the Streamlit dashboard (J) are still stubs. The fixture run exits 0 with
the two detections `fixtures/README.md` expects:

```
$ python -m air.detectors.no_fly_zone run \
    --input air/detectors/no_fly_zone/fixtures/tracks/klyh_mixed.json \
    --out out/

no_fly_zone: .../klyh_mixed.json
  config                 ok    baseline=nfz-rules-0.1.0+sua-2026-08-07
  B airspace_loader      ok    3 zones
  A adsb_loader          ok    5 states
  C-G pipeline           ok    2 detections
  output                 ok    out/detections.jsonl (2 detections)
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
├── live/                        experimental Flys Down live run (see below)
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

## Live run against Flys Down (experimental)

`live/` runs this same pipeline against the public aircraft feed of Project
Flys Down (flysdown.jaronwilson.dev) for KLYH at 150 NM, and can publish a
report the site shows in its own SkyWatch panel. It is a separate process, like
the collector; the stages it drives are unchanged and still pure. Settings are
in `config/live_flysdown.yaml`, so `config.yaml` is untouched.

```bash
pip install -e ".[dev,nfz]"

# One read-only evaluation of the live feed, report to a file:
python -m air.detectors.no_fly_zone.live --once --out out/report.json

# Replay the recorded fixtures (no network):
python -m air.detectors.no_fly_zone.live --once \
    --feed-file air/detectors/no_fly_zone/fixtures/flysdown/aircraft_klyh.json \
    --zones-file air/detectors/no_fly_zone/fixtures/flysdown/zones.json --out out/replay.json

# Keep running and publish to a Flys Down instance (local or live):
SKYWATCH_TOKEN=... python -m air.detectors.no_fly_zone.live --publish http://127.0.0.1:8795
```

What it will and will not claim:

- **Timing.** The feed has no per-aircraft timestamp. Observation time is
  estimated as the snapshot's `fetchedAt` minus the position's `seenPos`, and
  every detection says so. A record with no `seenPos` is skipped, never
  stamped with the fetch time. A snapshot over 30 s old, or one the feed marks
  stale, is not evaluated at all.
- **Activation.** Flys Down's `zones.json` does not model activation. An FAA
  prohibited area whose published times of use are `CONTINUOUS` is treated as
  always active (switch off with `zones.trust_published_continuous`); every
  other zone is NOTAM-activated, so stream E answers UNKNOWN and severity is
  capped. Missing activation data is never read as active.
- **Classes.** `confirmed_active` needs strict containment, the altitude band
  and ACTIVE activation. `activation_uncertain` and `buffered_only` are
  reported as such and are not violation claims.
- **Quiet vs broken.** A report says whether the feed was `fresh`, `stale` or
  `unavailable`, and whether evaluation ran; a quiet fresh run carries the exit
  reason for every state.

Results are experimental and not for navigation or operational decisions:
the geometry is Flys Down's simplified copy of the FAA boundary and no NOTAM,
TFR or waiver source is checked. Tests: `tests/test_live.py`.
