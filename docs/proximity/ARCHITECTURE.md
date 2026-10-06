# Architecture — `skywatch.proximity`

**Detector:** Dangerous / Unusual Proximity · **Version** 0.1.0 ·
**Config version** 2026-09-20.1 · **Status** MVP complete (Week 6)
**Team:** Paul Piwowarski (lead), Erik Ellis, Emmanuel Onwuka, Caleb G, Caleb K,
Caroline, Faith
**Maritime lineage:** SENTINEL M-003 Proximity / Rendezvous

---

## 1. What it does

Flags pairs of aircraft whose **predicted** separation at closest approach falls
below published separation standards within the next 120 seconds, assuming both
hold their current speed and track.

The distinction that defines the detector: **we do not measure current
distance.** Two aircraft 20 nm apart closing at 900 kt are a detection; two
aircraft 1 nm apart and diverging are not. Measuring present separation is a
distance readout; predicting future separation is a detector.

### Scope boundary

| In scope | Out of scope |
|---|---|
| Pairwise closest-approach prediction from ADS-B | Transport, storage, geospatial indexing |
| Severity assignment from a versioned rule set | Trust, governed Confidence, hard gates (TCE/CAATS owns these) |
| Detector-level uncertainty and factual evidence | Intent, threat assessment, case management |

We emit a `Detection`. A separate Xenith service decides what it means.

---

## 2. Pipeline

```
data/lynchburg_adsb.csv                           recorded Wingbits ADS-B
        │
        │  air/normalizers/wingbits_csv.py        column map, NaN → None,
        ▼                                         optional time / bbox window
list[AdsbObservation]                             the shared input contract
        │
        │  tracks.align_tracks                    interpolate each track onto a
        ▼                                         common 1-second grid
{tick: [AdsbObservation, ...]}                    a snapshot of the sky per second
        │
        │  pairs.candidate_pairs                  grid-cell binning, airborne
        ▼                                         check, vertical prefilter
[(AdsbObservation, AdsbObservation), ...]         pairs worth real math
        │
        │  features.pair_geometry                 relative position + velocity,
        ▼                                         t_cpa, predicted separation
PairGeometry                                      the feature record
        │
        │  rules.flag_pair                        gates, then the severity table
        ▼
SeverityLevel | None
        │
        │  detector.to_detection                  evidence, provenance, versions,
        ▼                                         explanation facts, limitations
Detection                                         the vendored SENTINEL contract
```

Orchestrated by `ProximityDetector.detect_observations()`, which runs every
stage and reduces each aircraft pair to a single detection.

---

## 3. Modules

All paths relative to the repository root.

| Module | Responsibility | Public API |
|---|---|---|
| `air/normalizers/wingbits_csv.py` | Recorded CSV → `AdsbObservation`. Shared enabling work; usable by all three detector teams. | `load_wingbits_csv`, `COLUMN_MAP`, `REQUIRED` |
| `air/detectors/proximity/config.py` | Load and validate the YAML rule set into a frozen dataclass. | `load_config`, `ProximityConfig`, `SeverityTier` |
| `air/detectors/proximity/tracks.py` | Time alignment. Group by aircraft, interpolate onto a fixed grid, assemble per-tick snapshots. | `group_tracks`, `interpolate_to_grid`, `align_tracks` |
| `air/detectors/proximity/pairs.py` | Candidate generation. Spatial binning and the cheap rejects. | `cell_of`, `is_airborne`, `candidate_pairs` |
| `air/detectors/proximity/geometry.py` | Pure scalar geometry. No objects, no state. | `haversine_nm`, `to_local_xy`, `velocity_xy`, `time_to_cpa`, `predicted_separation` |
| `air/detectors/proximity/features.py` | The `PairGeometry` record — the contract between the math and the rules. | `PairGeometry`, `pair_geometry` |
| `air/detectors/proximity/rules.py` | Gates and the severity table. Reads every number from config. | `severity_for`, `flag_pair` |
| `air/detectors/proximity/detector.py` | Scoring, the `Detection` contract, and the `BaseDetector` subclass. | `confidence_for`, `explanation_facts`, `to_detection`, `ProximityDetector` |
| `configs/detectors/proximity.yaml` | Every threshold, versioned. | — |
| `scripts/run_proximity.py` | CLI runner: fixture in, Detection JSON out. | — |
| `scripts/make_proximity_fixtures.py` | Deterministic generator for the synthetic corpus. | — |

### Design rules the modules obey

- **Pure functions.** Same input, same output. No I/O, no globals, no mutation
  of arguments, outside the normalizer and the CLI runner.
- **No service dependencies.** No database, no network in any code path. Every
  function is testable against a hand-built fixture.
- **Abstain over guess.** Missing evidence returns `None` / `False` / `[]`. A
  pair we cannot judge must not produce a detection.
- **Thresholds live in config.** No numeric literal in logic code.
- **`contracts/` is read-only.** We import `Detection`; we never redefine it.

---

## 4. Stage detail

### 4.1 Normalization — `wingbits_csv.load_wingbits_csv`

Maps the short Wingbits/readsb column codes onto `AdsbObservation`:

| CSV | Field | | CSV | Field |
|---|---|---|---|---|
| `h` | `icao24` | | `tr` | `track_deg` |
| `timestamp` | `observed_at` | | `br` | `vertical_rate_fpm` |
| `la` / `lo` | `latitude` / `longitude` | | `n` / `np` | `nic` / `nacp` |
| `ab` | `altitude_ft` | | `f` | `callsign` |
| `gs` | `ground_speed_kt` | | | |

Two decisions carry downstream consequences:

- **Barometric altitude only (`ab`), never geometric (`ag`).** The feed carries
  both; mixing them across a pair invents vertical separation. The sample's
  first row differs by 350 ft between the two.
- **pandas `NaN` is converted back to `None`.** `NaN` is a float and survives
  every `is not None` check, which would silently defeat the abstain rules.

Rows missing ICAO, timestamp, or position are dropped rather than imputed.
Optional `start` / `end` / `bbox` windows filter before object construction.

### 4.2 Time alignment — `tracks.interpolate_to_grid`

**Why this is step one, not an optimization.** ADS-B reports arrive at
irregular intervals. Comparing aircraft A at 12:00:03 against aircraft B at
12:00:07 invents conflicts that never happened — at jet speed, four seconds is
roughly half a nautical mile. This is the dominant source of phantom detections
in any proximity analytic.

Implementation notes:

- Timestamps are handled as **integer microseconds since epoch**; `step_s` is
  rejected unless it is a whole number of microseconds, because `datetime`
  cannot represent a finer grid.
- Ticks are computed arithmetically per segment (`ceil(before/step) ..
  floor(after/step)`), not by walking the clock, so a long silence costs the
  same as a short one.
- Linear blend for position, altitude, speed, vertical rate; **short-way-round**
  blend for compass track, so 350° → 10° passes through 0 and not 180.
- A tick landing exactly on a real report returns that report untouched.
- Segments longer than `max_gap_s` (30 s) are **not** blended across — only the
  real endpoints survive. We do not invent positions through a receiver outage.

### 4.3 Candidate generation — `pairs.candidate_pairs`

All-pairs comparison is O(n²): roughly 400,000 comparisons per second of data at
900 aircraft. Instead:

1. Drop anything not airborne, or missing track or ground speed.
2. Bucket into 0.5° lat/lon cells (~30 nm) via `cell_of`.
3. Compare each cell against itself and its eight neighbours only.
4. Reject pairs sharing an ICAO, or separated by more than
   `max_vertical_prefilter_ft` (2000 ft).

`is_airborne` is a backup for the unreliable broadcast on-ground flag — which
`AdsbObservation` does not currently carry at all (see §9). An aircraft is on
the ground only when **both** below `ground_altitude_ft` and slower than
`ground_speed_kt`. Low and fast is final approach; high and slow is a helicopter
hovering. Both are flying.

### 4.4 Features — `features.pair_geometry`

Builds the frozen `PairGeometry` record. Work is done in a local flat plane
centred on aircraft A, which sits at the origin:

| Quantity | Computation |
|---|---|
| Relative position `r` | `to_local_xy(B)` — equirectangular, metres east/north |
| Relative velocity `v` | `velocity_xy(B) − velocity_xy(A)` — m/s from knots + compass track |
| Closure rate | `−(r·v)/\|r\|`, reported in knots; positive means closing |
| `t_cpa` | `−(r·v)/\|v\|²`; `None` when relative velocity is ~0 |
| Predicted separation | `\|r + v·t\|` horizontally; `\|Δalt + Δrate·t/60\|` vertically |

The equirectangular projection is accurate to a few metres within ~50 nm, which
is well inside the range at which pairs are considered.

### 4.5 Rules — `rules.flag_pair`

Gates first; any failure returns `None`:

1. `t_cpa` exists (relative velocity is non-zero)
2. `t_cpa > 0` — converging, not already past closest approach
3. `t_cpa ≤ max_tcpa_s` (120 s) — beyond that, constant-heading prediction is
   not trustworthy
4. Predicted separations are not `None`

Then `severity_for` walks the tier table top to bottom and returns the first
tier where **both** limits hold. Comparisons are strict `<`, so a value exactly
on a boundary falls to the next tier down.

### 4.6 Output — `detector.to_detection`

Emits the vendored SENTINEL `Detection`:

| Field | Contents |
|---|---|
| `detector_id` / `detector_version` | `skywatch.proximity` / `0.1.0` |
| `detection_type` | `predicted_proximity` |
| `severity` | From the tier table |
| `confidence` | Certainty about the **geometry**, not about threat. Falls linearly from 1.0 at `t_cpa = 0` to 0.5 at `max_tcpa_s`, since straight-line prediction degrades with lookahead. |
| `entities_involved` | Exactly two `EntityRef`s, `aircraft:<icao24>` |
| `temporal_bounds` | Observation instant → predicted closest approach |
| `evidence` | Predicted-closest-approach record with all features in metadata, plus an aircraft-state record |
| `provenance` | Source system, raw refs, and a `ProcessingStep` carrying the **entire config** as parameters |
| `geospatial_context` | Midpoint of the pair, current separation in metres |
| `metadata` | `explanation_facts`, `limitations`, `feature_schema_version`, `baseline_or_model_version` |

**Deduplication (MVP level):** one detection per aircraft pair per run, keeping
the instant with the smallest predicted horizontal separation. A 90-second
encounter produces one event, not 90. Encounter-level session logic is Week 9+.

---

## 5. Configuration

All thresholds live in `configs/detectors/proximity.yaml` and are loaded into a
frozen `ProximityConfig`. The whole config is written into every detection's
provenance, so any historical result can be explained by the exact rules that
produced it.

| Key | Value | Rationale |
|---|---|---|
| `grid_step_s` | 1.0 | Time-alignment resolution |
| `max_gap_s` | 30.0 | Longest silence we will interpolate across |
| `cell_size_deg` | 0.5 | ~30 nm spatial bin |
| `max_vertical_prefilter_ft` | 2000 | Cheap reject before CPA math |
| `ground_altitude_ft` / `ground_speed_kt` | 3000 / 50 | Backup ground check |
| `max_tcpa_s` | 120.0 | Prediction-horizon limit |

**Severity tiers** — both conditions must hold:

| Severity | Horizontal | Vertical |
|---|---|---|
| HIGH | < 0.5 nm | < 400 ft |
| MEDIUM | < 1.5 nm | < 700 ft |
| LOW | < 3 nm | < 1000 ft |
| INFO | < 5 nm | < 1000 ft |

Derived from published standards: en route 5 nm / 1000 ft, terminal 3 nm /
1000 ft, FAA near-midair-collision under 500 ft total. Every number is
defensible by citation rather than by tuning.

---

## 6. Testing

**129 tests, no services, no network.** CI runs the full suite on every pull
request (`.github/workflows/tests.yml`).

| Suite | Tests | Covers |
|---|---|---|
| `test_proximity_tracks.py` | 45 | Grid ticks, blending, angle wrap, gap handling, duplicate timestamps, float-precision boundaries, invalid input, performance guard |
| `test_proximity_rules.py` | 19 | Severity table at 12 boundary values, both-limits rule, gates |
| `test_proximity_geometry.py` | 17 | Projection, velocity decomposition, `t_cpa` sign, predicted separation |
| `test_proximity_pairs.py` | 14 | Airborne logic, cell neighbours, every cheap reject |
| `test_wingbits_csv.py` | 11 | Column mapping, barometric choice, `NaN` → `None`, filters, malformed rows |
| `test_proximity_detector.py` | 9 | End-to-end on all five fixtures, contract shape, governance wording |
| `test_proximity_config.py` | 4 | YAML load, tier ordering, provenance serialization |

### Synthetic corpus

Real dangerous-proximity events are rare and unlabeled, so
`scripts/make_proximity_fixtures.py` scripts encounters where the answer is
known **by construction**: choose the geometry at closest approach, then run the
clock backwards to produce the starting positions. Every scenario reports on
deliberately mismatched, irregular timestamps.

| Fixture | Expected |
|---|---|
| `proximity_head_on.json` | 1 detection, HIGH |
| `proximity_crossing_low.json` | 1 detection, LOW |
| `proximity_diverging.json` | 0 — `t_cpa` negative |
| `proximity_stacked.json` | 0 — vertical prefilter |
| `proximity_ground.json` | 0 — both on the ground |

---

## 7. Measured behaviour

Recorded Wingbits ADS-B, 2026-09-01 00:00–01:00 UTC, 200 nm around Lynchburg VA:

| | |
|---|---|
| Observations | 284,476 |
| Distinct aircraft | 915 |
| Median report interval | 2.4 s |
| Load time | ~5 s |
| Detection time | ~30 s |
| **Detections** | **531** (24 HIGH · 52 MEDIUM · 200 LOW · 255 INFO) |

These results are **unreviewed**. No claim is made about how many represent
genuine conflicts; see §8.

Illustrative output, showing why prediction rather than measurement matters:

```
LOW  a2dffe/a441d6   predicted 0.00 nm / 944 ft at t+82 s
                     currently 20.5 nm apart, closing at 907 kt
```

A current-distance check would never surface that pair.

---

## 8. Known limitations

Carried in every detection's `limitations` field:

- Prediction assumes constant ground speed and track for both aircraft.
- Positions are linearly interpolated between received reports.
- Controller clearances and pilot intent are not observable from ADS-B.
- Barometric altitude only; geometric altitude is ignored.

Additional, at the system level:

- **No ground truth.** Nobody labels near-misses in ADS-B. Evaluation rests on
  synthetic scenarios with constructed answers plus manual review
  (`docs/proximity/REVIEW_SHEET.md`).
- **No context filtering yet.** Approach sequencing — aircraft legitimately 3 nm
  in trail for the same runway — is expected to dominate false positives and is
  not yet suppressed.
- **Duplicate or changing ICAO codes** register as a perfect self-conflict. One
  such candidate pair was observed in the Lynchburg run (adjacent hex codes,
  42 ft apart, 3 kt closure — almost certainly formation or a duplicate
  transponder).
- **Fixed cell size.** At high closure rates a pair more than one cell apart can
  still matter within the 120 s horizon.
- **Ground check uses a single MSL altitude.** Field elevations vary; the speed
  check does most of the work.

---

## 9. Interfaces and dependencies

**Consumes:** `air/models/observation.py::AdsbObservation` (shared input
contract). **Produces:** `contracts/detection.py::Detection` (vendored SENTINEL
output contract, read-only).

**Runtime dependencies:** Python ≥ 3.11, `pandas` ≥ 2.0, `pyyaml` ≥ 6.0.
Development adds `pytest`. No database, no services, no ML libraries, no numpy —
the geometry is standard-library `math`.

### Open items for the Technical Lead

1. **`AdsbObservation` has no `on_ground` field.** The Wingbits feed carries
   `og` and the normalizer currently drops it; every detector would benefit from
   the shared model carrying it.
2. **Multi-entity detections.** The syllabus's example output shows a single
   `entity_ids` element. Proximity always emits two. Confirm the TCE/CAATS path
   handles multi-entity detections before Week 11.
3. **Airport reference data (FAA NASR)** is required for Week 9 context
   filtering — runway alignments and field elevations. Not yet sourced.

---

## 10. Roadmap

| Week | Deliverable | Status |
|---|---|---|
| 4 | Features + positive/negative test cases | Complete |
| 5 | Versioned rule set | Complete |
| **6** | **MVP — ≥ 1 valid Detection on replay data** | **Complete** |
| 7 | Labeled evaluation set + success metrics | Review sheet drafted |
| 8 | v0.2 with quantified performance | |
| 9 | False-positive analysis + ≥ 1 mitigation (approach sequencing) | |
| 10 | v0.3 improves a defined metric | |
| 11 | TCE/CAATS integration | |
| 12 | Fails safely on stale data, missing fields, receiver outage | Abstain paths in place |
| 13 | Deterministic explanations | `explanation_facts` in place |
| 14 | Integration rehearsal, clean checkout | |
| 15 | Final demo and handoff | |

---

## 11. Running it

```bash
pip install -e ".[dev,eda]"
pytest -q                                                      # 129 passed
python scripts/run_proximity.py air/fixtures/proximity_head_on.json
```

Against recorded traffic:

```python
from air.normalizers.wingbits_csv import load_wingbits_csv
from air.detectors.proximity import ProximityDetector

observations = load_wingbits_csv("data/lynchburg_adsb.csv")
detections = ProximityDetector().detect_observations(observations)
```

---

## 12. Related documents

| Document | Contents |
|---|---|
| [`DESIGN_CARD.md`](../../air/detectors/proximity/DESIGN_CARD.md) | One-page design card (required deliverable) |
| [`PROJECT_PLAN.md`](PROJECT_PLAN.md) | Full project plan, thresholds rationale, false-positive catalogue |
| [`TASKS.md`](../../air/detectors/proximity/TASKS.md) | Task board and ownership |
| [`PR_GUIDE.md`](PR_GUIDE.md) | Branch model, PR format, review checklist |
| [`REVIEW_SHEET.md`](REVIEW_SHEET.md) | Manual evaluation sheet (Week 7) |
| Per-function write-ups | `geometry.md`, `interpolate_to_grid.md`, `candidate_pairs.md`, `rules.md`, `detect_observations.md`, `wingbits_csv.md` |
