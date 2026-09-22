# SkyWatch — Dangerous Proximity Detector

Liberty University AI Club, Fall 2026. Sponsored by Xenith Solutions.

> The team's reference document. If you are filling in the
> [Detector Design Card](../../air/detectors/proximity/DESIGN_CARD.md), every
> answer is somewhere in here. If you are writing code, your task card is in
> [TASKS.md](../../air/detectors/proximity/TASKS.md) and the pipeline is
> summarised in [the detector README](../../air/detectors/proximity/README.md).

## What this project is

We are building the **air-domain extension** to Xenith's existing SENTINEL platform,
a multi-domain surveillance system that currently watches maritime traffic.

Three student teams each build one detector. Our team owns **dangerous / unusual
proximity**: flagging pairs of aircraft projected to pass closer to each other than
their situation warrants.

We are NOT building SENTINEL. Transport, provenance, geospatial indexing, trust
scoring, audit, and case management already exist and are reused. Do not reimplement
platform infrastructure.

## Our detector in one sentence

Ingest ADS-B aircraft telemetry, project every aircraft forward using speed and
heading, and emit a detection when a pair's *predicted* separation at closest
approach drops below threshold.

The key distinction: we do not measure current distance. We predict future
separation. That is what makes this a detector rather than a distance readout.

## Maritime lineage

This is a direct adaptation of SENTINEL's **M-003 Proximity / Rendezvous** detector,
which finds ships sitting close together for at-sea cargo transfers. Same spatial
join, inverted time signature — ships matter when they *linger*, aircraft matter when
they *converge*.

"At least one detector directly adapts a maritime analytic pattern" is a stated
semester success criterion. Our team carries it.

## Algorithm

1. **Load** recorded ADS-B observations (replay data, not live, for repeatability)
2. **Time-align** — interpolate every aircraft track onto a common 1-second grid.
   This is not optional. Positions arrive at irregular intervals; comparing A's
   position at 12:00:03 against B's at 12:00:07 invents conflicts that never
   happened. This is the single most common source of phantom detections.
3. **Spatial binning** — drop aircraft into grid cells, only compare pairs in the
   same or adjacent cells. All-pairs comparison is O(n^2) and will not scale.
4. **Cheap filters first** — drop pairs with vertical separation > 2000 ft; drop
   pairs where either aircraft is on the ground.
5. **Relative vectors** — compute relative position `r` and relative velocity `v`
   for the pair.
6. **Time to closest approach** — `t_cpa = -(r . v) / |v|^2`.
   Negative means diverging; drop it.
7. **Predicted separation** at `t_cpa`, horizontal and vertical.
8. **Threshold** → severity tier (see below).
9. **Context filters** — suppress or downgrade approach sequencing, parallel
   approaches, formation flight.
10. **Deduplicate** — a 90-second encounter must produce ONE event, not 90 alerts.
11. **Emit** the Detection object.

Steps 1–8 are the MVP (due Week 6). Steps 9–10 come in Weeks 9–11.

## Thresholds

We are a **rule-based detector**, not a learned model. Thresholds derive from
published aviation separation standards, which makes every number defensible:

- En route standard separation: 5 nm horizontal, 1000 ft vertical
- Terminal / approach separation: 3 nm horizontal, 1000 ft vertical
- FAA near-midair-collision definition: under 500 ft total separation

Severity tiers, based on **predicted** separation at closest approach:

| Severity | Horizontal | Vertical |
|----------|------------|----------|
| HIGH     | < 0.5 nm   | < 400 ft |
| MEDIUM   | < 1.5 nm   | < 700 ft |
| LOW      | < 3 nm     | < 1000 ft |
| INFO     | < 5 nm     | < 1000 ft |

Both conditions must hold. Two aircraft 0.2 nm apart horizontally but 2000 ft apart
vertically are legally and operationally fine.

Additional gates:
- Time to closest approach under **120 seconds** (beyond that, constant-heading
  prediction is unreliable)
- Pair must be **converging**, not diverging
- Both aircraft **airborne**

All thresholds live in a versioned config file. They are not hardcoded.
See [`configs/detectors/proximity.yaml`](../../configs/detectors/proximity.yaml).

## Inputs

From ADS-B (note: `timestamp` is applied by the receiver, not broadcast by the
aircraft):

`icao24`, `callsign`, `timestamp`, `lat`, `lon`, `baro_altitude`, `ground_speed`,
`track`, `vertical_rate`, `on_ground`, `NIC`, `NACp`

Column names vary by source — OpenSky uses `baroaltitude` and `velocity`; tar1090
differs again. Always confirm against the actual file.

Reference data required:
- **Airport locations and runway alignments** (FAA NASR) — needed for context
  filtering. Without this, approach traffic dominates our false positives.
- **FAA aircraft registry** — hex code to type/operator, to distinguish helicopters
  from airliners.

`on_ground` is broadcast but not always set correctly. Back it up with a
low-altitude, low-speed check.

## Computed features

Per pair: horizontal separation (haversine), vertical separation, closure rate,
time to CPA, predicted CPA distance, converging flag, track angle difference.

From context: distance to nearest airport, alignment with runway heading,
descending flag.

## Output contract

Every detection emits this exact shape. All fields required.

```json
{
  "detector_id": "skywatch.proximity",
  "detector_version": "0.1.0",
  "entity_ids": ["aircraft:<icao24>", "aircraft:<icao24>"],
  "detection_type": "string",
  "severity": "INFO|LOW|MEDIUM|HIGH",
  "anomaly_score": 0.0,
  "raw_model_confidence": 0.0,
  "evidence_refs": ["observation-or-track-id"],
  "feature_schema_version": "air-features-v1",
  "baseline_or_model_version": "string",
  "explanation_facts": ["structured factual statement"],
  "limitations": ["known caveat"]
}
```

Notes:
- `entity_ids` is an **array**. Proximity always involves exactly two aircraft.
  This is why the field is plural.
- `anomaly_score` = how far outside normal. `raw_model_confidence` = how sure we are
  about that. They are different numbers.
- Version fields exist so a detection from six weeks ago can be explained. Populate
  them from day one; retrofitting is miserable.

> **In this repo** we emit the real vendored SENTINEL `Detection` dataclass from
> `contracts/`, which carries the same information in a richer shape:
> `entities_involved` (the two aircraft), `evidence`, `provenance`,
> `temporal_bounds`, and `explanation_facts` / `limitations` /
> `feature_schema_version` / `baseline_or_model_version` under `metadata`.
> See `to_detection()` in `air/detectors/proximity/detector.py`.

## Governance rules — do not violate

- **We do not calculate Trust.** We supply evidence and detector-level uncertainty.
  A separate service (TCE/CAATS) evaluates governed Confidence, Trust, hard gates,
  and assurance.
- **Detector confidence describes certainty about a deviation. It does not
  establish intent or threat.** Two aircraft close together is an observation.
  Whether it was dangerous depends on clearances and controller instructions we
  cannot see.
- `explanation_facts` contain observations, never conclusions. State distance,
  altitude, and time to closest approach. Never the word "dangerous" or
  "violation."
- The project reports on **airspace patterns**, not on named aircraft or the people
  flying them. No individual tail gets singled out in demos.

## False positives — the real work

Ranked by expected impact:

1. **Approach sequencing** — aircraft lined up to land are legitimately 3 nm in
   trail. Dominant false positive source. Mitigate by suppressing pairs aligned on
   the same runway heading, descending, near an airport.
2. **Parallel approaches** — parallel runways put aircraft 1 nm apart laterally as
   normal operations. Detect near-parallel tracks converging slowly, downgrade.
3. **Timestamp misalignment** — see algorithm step 2.
4. **Vertical-only separation** — stacked 1000 ft apart is normal. Vertical gate
   handles it.
5. **Formation flight** — military, training, air shows. Deliberately close.
6. **Ground traffic** — taxiing aircraft are meters apart.
7. **Altitude type mismatch** — ADS-B carries both barometric and geometric
   altitude. Mixing them across a pair produces fake vertical separation. Pick one,
   be consistent.
8. **Helicopters** — low altitude near hospitals and heliports, different rules.
9. **Duplicate / changing ICAO codes** — an aircraft appearing twice registers as a
   perfect self-conflict.
10. **Search and rescue, joint military operations** — multiple aircraft
    intentionally working the same small volume.

The pattern: every one is a case where "close" is the point. The detector only sees
distance, not intent.

## Data sources

- **OpenSky Network** — historical state vectors, free for research. Primary offline
  dataset. **Known limitation: 10-second sampling.** At jet speeds that is over a
  nautical mile of travel between rows, which is coarse for conflict detection.
  Interpolate, and be honest about this in evaluation.
- **Club tar1090 receiver** — live local feed. Finer resolution. Typically exposes
  aircraft data as JSON; check for an API endpoint rather than scraping.
- **FAA NASR** — airport and runway data.
- **FAA aircraft registry** — type and operator lookup.
- **Synthetic anomalies** — scripted converging pairs with known ground truth.
  Essential, because real dangerous-proximity events are rare and unlabeled.

> **What we actually have so far:** `data/lynchburg_adsb.csv` — one hour
> (2026-09-01 00:00–01:00 UTC) of Wingbits network ADS-B within 200 miles of
> Lynchburg, VA. 284k rows, 915 aircraft, median 2.4 s between reports (much
> finer than OpenSky's 10 s). Plus five synthetic scenarios in
> `air/fixtures/proximity_*.json` with answers known by construction.

## Ground truth

Nobody labels near-misses in ADS-B data. Our approach:
- Manual review of flagged pairs, recorded in a labeled evaluation set
- Synthetic scenarios where the answer is known by construction

Be honest about this rather than overclaiming.

## Semester milestones

| Week | Deliverable |
|------|-------------|
| 2 | Detector design card |
| 3 | Consumes shared normalized fixtures |
| 4 | Features + positive/negative test cases |
| 5 | Versioned rule set (our "baseline") |
| 6 | **MVP — at least one valid Detection on replay data** |
| 7 | Labeled evaluation set + success metrics |
| 8 | Mid-semester review; v0.2 with quantified performance |
| 9 | False-positive analysis, at least one mitigation |
| 10 | v0.3 improves a defined metric |
| 11 | TCE/CAATS integration |
| 12 | Fails safely on stale data, missing fields, receiver outage |
| 13 | Deterministic explanations on every detection |
| 14 | Integration rehearsal, clean checkout |
| 15 | Final demo and handoff |

## Constraints

- Team of 3–5 students
- **~2 hours per week total** (1 hr club meeting + 1 hr team meeting)
- Required milestones cannot depend on substantial extra hours
- Scope every task to fit this. Prefer the smallest thing that works.

## Working preferences

- Python. pandas and numpy for data work.
- Thresholds in config, never hardcoded.
- Write tests against synthetic fixtures with known answers.
- Every detection must be reproducible from recorded data plus a version number.
- Keep the Pi/receiver side dumb; all analysis happens downstream.

## Open questions to resolve

- What do TCE and CAATS stand for, and where is the interface?
- Who provides the captured ADS-B fixtures?
- Does the club receiver expose a JSON API?
- What are the code ownership and attribution terms with Xenith?
