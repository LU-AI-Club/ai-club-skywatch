# SkyWatch — Repo Context & SENTINEL Architecture

Context for a model working in the `ai-club-skywatch` repo. It explains **what
this repo is, how it must be built, and the larger SENTINEL system it plugs
into** — so any change you make fits the overarching picture. No specific task
is assumed here.

---

## 1. What SkyWatch is

SkyWatch is the **Liberty University AI Club's aerospace-domain extension of the
Xenith SENTINEL platform**. SENTINEL is a multi-domain threat-detection system
whose first mission is maritime (tracking the "dark fleet" from AIS data).
SkyWatch adds the **air domain**: detectors over **ADS-B** aircraft data.

Three student teams each own one detector:
- `air/detectors/spoofing/` — ADS-B spoofing / position inconsistency
- `air/detectors/proximity/` — dangerous / unusual aircraft proximity
- `air/detectors/no_fly_zone/` — no-fly-zone / airspace violation

The students are mostly new to software engineering. Everything is structured so
a beginner can complete one small, independently testable task at a time.

---

## 2. SENTINEL architecture — the overarching picture

**SENTINEL** (Surveillance, Evaluation, and Network Threat Intelligence for
Linked Entities) is an environment-agnostic platform that detects and analyzes
threats across **maritime, air, and space** domains. Its central idea: every
tracked thing — vessel, aircraft, satellite — is an instance of one abstract
`ObservedEntity`, so the same fabric, analytics, and governance serve all
domains.

### Design principles (these shape every decision)
1. **Domain agnosticism** — core types are abstract; maritime/air/space are
   extensions, not forks.
2. **Schema-on-read** — raw data stored natively; schema applied at query time
   via mapping profiles.
3. **Analytic durability** — append-only, versioned; old data stays queryable as
   detectors evolve.
4. **Lineage by default** — every record carries provenance; nothing is
   unattributed.
5. **Policy-aware handling** — classification/handling travels *with* the data.
6. **Federated first** — computation can move to the data across nodes.
7. **Environment agnosticism** — containers only; cloud, on-prem, or air-gapped.

### The layered pipeline (bottom to top)
```
SOURCE            raw feeds (AIS; for SkyWatch: ADS-B / OpenSky / local receiver)
INGESTION         connectors → normalizers → quality gates → provenance tagging
STORAGE           data lake (raw) · graph DB (Neo4j/AGE) · geo index (PostGIS+H3) · time series
PROCESSING        stream · batch · ML pipeline
FUSION/DETECTION  detectors consume observations → emit Detections
GOVERNANCE        catalog · policy engine · access control · trust/source classification
SEMANTIC          schema registry · ontology · mission profiles · confidence/provenance
CONSUMER          dashboards · APIs · notebooks · federated queries · alerting
```

### Core domain model
- `ObservedEntity` → `identity`, `observations`, `behaviors`, `relationships`,
  `risk_profile`, `lineage`, `tags`. Domain subclasses: `Vessel`, `Aircraft`,
  `SpaceObject`.
- `Observation` → `timestamp`, `position` (`GeoPosition`), `kinematics`,
  `source`, `quality`, `provenance`.

### Detection framework
- Every detector subclasses `BaseDetector` and implements `detect(context) ->
  list[Detection]` and `get_required_data() -> DataRequirements`.
- A `Detection` carries: `detector_id`/`detector_version`, `detection_type`,
  `severity`, `confidence`, `entities_involved`, `evidence`,
  `geospatial_context`, `temporal_bounds`, `provenance`, `tags`, and optional ML
  attributions. It serializes with `.to_dict()`.
- Detectors declare an `implementation_type` (`RULE_BASED` / `MACHINE_LEARNING`)
  that governance gates read.

### TCE/CAATS — the trust boundary (critical to understand)
Detectors do **not** decide truth or threat. A detector supplies **evidence and
its own detector-level uncertainty**. The platform's **TCE/CAATS** services (the
Trust & Confidence Engine and its assurance/scoring layer) then evaluate
governed **Confidence, Trust, hard gates, provenance, operational context, and
assurance**, and compose detections into higher-order `AnalyticCase`s. So:
- A detector's `confidence` describes certainty about a **deviation** — never
  intent or threat.
- Teams **never compute Trust** or build the case/scoring logic; they emit a
  well-formed `Detection` with evidence + provenance, and it flows into the
  existing TCE path unchanged. (Maritime references: `DETECTOR_TCE_BOUNDARY.md`,
  `TCE_ARCHITECTURE.md`, `TRUST_SEMANTICS.md` in the SENTINEL repo.)

### How a new domain is added (the pattern SkyWatch follows)
Adding a domain requires only four things; the fabric, graph/geo engines,
provenance, and policy engine need **zero modification**:
1. **Domain entity extension** (e.g. `Aircraft`),
2. **Domain connectors** (ingest the raw feed),
3. **Domain detectors** (the algorithms),
4. **Domain normalizers** (raw → the common `Observation` model).

Maritime already implements this pattern end to end (connectors for
MarineCadastre/GFW/sanctions; normalizers; detectors M-001…M-013 such as AIS gap,
spoofing, proximity/rendezvous, risk-zone entry, route deviation, fleet
clustering). **SkyWatch is the air-domain instance of the same four components** —
and its detectors deliberately adapt maritime analogues (e.g. air proximity ≈
maritime M-003; no-fly-zone ≈ maritime risk-zone entry; spoofing ≈ maritime AIS
spoofing).

---

## 3. How SkyWatch maps onto SENTINEL

- `contracts/` is a **vendored, read-only copy** of SENTINEL's detection output
  contract (`Detection`, `Evidence`, `ProvenanceRecord`, `BaseDetector`, …).
  Emitting the *real* `Detection` is what lets a SkyWatch detector flow into the
  real TCE/CAATS pipeline without a rewrite. **Import these; never redefine
  them.** See `contracts/README.md`.
- `air/` is the air-domain extension: `air/models/` (entity/observation
  contracts), `air/normalizers/` (raw ADS-B → `AdsbObservation`), and
  `air/detectors/` (the three detectors).
- This repo intentionally **omits** the heavy platform infrastructure (data lake,
  Kafka, PostGIS, graph DB, the TCE engine itself). Detectors run as pure Python
  on in-memory dataclasses so beginners need no services. Those systems exist on
  the real platform; here we only honor the **contracts** at the seams.

---

## 4. Repo conventions (do not violate)

- **Detectors are pure Python on dataclasses. No database, no network, no
  services in the detector code path.** Streaming, DB access, and live feeds are
  *enabling infrastructure* (Tech-Lead-owned) that call into detectors — never
  baked inside them.
- **Input contract:** `air/models/observation.py → AdsbObservation` (frozen
  dataclass, has `.from_dict()`). Detectors take a `list[AdsbObservation]`, via
  the convention `detector.detect_observations(obs_list)`.
  Fields: `icao24, observed_at (UTC, tz-aware), latitude, longitude, altitude_ft,
  ground_speed_kt, track_deg, vertical_rate_fpm, nic, nacp, squawk, callsign,
  receiver_id`.
- **Output contract:** the `Detection` from `contracts/` (read-only). If a
  shared/team-owned contract (like a feature-record dataclass) must change, one
  PR adds the field, updates the producer, and the change is announced so
  downstream owners rebase — treat shared shapes carefully.
- **Worked reference:** `air/detectors/_example_altitude/` is a complete, trivial,
  passing detector showing the whole skeleton (config → pure flag function →
  scoring → emit `Detection` → `BaseDetector`), with tests in
  `tests/air/detectors/test_example_altitude.py`. **Copy its shape**; a real
  detector is the same skeleton with a harder middle.
- **Six lanes & definition of done:** see `docs/DETECTOR_PLAYBOOK.md`. A detector
  splits into EDA+fixtures, feature engineering, baseline/reference, core logic,
  scoring+output, evaluation+false-positives. DoD for any task = a merged PR with
  the function **plus a `pytest` test on a fixture, no services**.
- **Abstain over guess:** when evidence is insufficient (missing fields, too few
  points), return nothing rather than emit a weak detection.
- The three detector folders are **student-owned**. Build enabling
  infra/scaffolding and fix shared contracts, but **do not implement the
  students' detector logic for them** unless explicitly asked.

---

## 5. Repo map & where to start

```
contracts/                 vendored SENTINEL contract — READ ONLY (Detection, provenance, BaseDetector)
air/
  models/observation.py    AdsbObservation — the shared input contract
  normalizers/             raw ADS-B -> AdsbObservation (shared enabling work)
  fixtures/                small committed test data (shared corpus)
  detectors/
    _example_altitude/     worked reference detector (copy its shape)
    spoofing/ proximity/ no_fly_zone/   team-owned detectors
configs/detectors/         per-detector YAML config
notebooks/                 EDA
scripts/                   CLI runners (one per detector / for feeds)
tests/                     mirrors air/, fixture-based, no services
docs/
  DETECTOR_PLAYBOOK.md     the six-lane parallel model + DoD (read this)
  CONTRIBUTING.md          branch → test → PR loop for beginners
data/                      local datasets (not all committed; see .gitignore)
```
Read, in order: `README.md` → `docs/DETECTOR_PLAYBOOK.md` →
`air/detectors/_example_altitude/` → `contracts/README.md`.

## 6. How to run

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install ".[dev]"
pytest -q                        # should be green
```

## 7. Working preferences (from prior sessions)

- **Deliver files; avoid running shell/verification commands that trigger
  permission prompts.** Reason about correctness and hand the user the exact
  `pytest`/run command to execute themselves.
- Build the **bones / enabling infrastructure**, not the students' detector
  logic.
