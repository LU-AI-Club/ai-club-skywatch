# Detector Playbook

How a team of 5–7 turns one detector into parallel, beginner-sized tasks.

## The one idea

A detector looks like one big program, but it is really a **pipeline of small
pure functions**: each takes plain data in and returns plain data out, with
**no database and no network**. So each function can be built and tested on its
own, by a different person, against a shared *contract* — before anyone else's
code is finished.

```
AdsbObservation[]                     (shared input contract: air/models/observation.py)
      │  build features
      ▼
<your feature record>[]               (the contract your team freezes in Week 3)
      │  flag rule
      ▼
events[]
      │  score + emit
      ▼
Detection                             (shared output contract: contracts/)
```

A **contract** is an agreed data structure at a boundary. Once frozen, everyone
downstream builds against the *shape*, not against your unfinished code. That is
what makes the work parallel.

## The six lanes

Assign an owner to each (pair up on a 7-person team). Every lane works on the
same detector but a different stage.

| Lane | Owns | Needs a DB? |
|------|------|-------------|
| 1. EDA + Fixtures | explore the data; build positive/negative fixture files everyone tests against | no |
| 2. Feature engineering | raw `AdsbObservation` → your feature-record dataclass | no |
| 3. Baseline / reference | defines & versions "normal" (envelopes, zones, corridors) | no |
| 4. Core detector logic | the flag rule — pure functions over feature records | no |
| 5. Scoring + output | confidence/severity + emit the `Detection` contract | no |
| 6. Evaluation + false positives | metrics, threshold sweeps, benign look-alikes | no |

The Technical Lead (and Xenith) own the DB, the live normalizer, and TCE/CAATS
wiring — **not** the detector teams.

## Definition of done (every task)

> A merged pull request containing the function **plus a `pytest` test that runs
> on a fixture — no database, no services.**

If a task can't be tested without standing up Postgres, it's the wrong task —
split it until the piece in front of you is a pure function on a dataclass.

## How to actually start (maps to the syllabus 15-week plan)

1. **Weeks 1–2:** the whole team does EDA together in `notebooks/`. This is the
   on-ramp — no scaffolding, just look at real ADS-B. Then write the Detector
   Design Card: the card's outputs *are* your two contracts (the feature-record
   fields, and confirmation you'll emit `Detection`).
2. **Week 3:** freeze the feature-record dataclass. **This is the fork point** —
   after it, all six lanes run in parallel.
3. **Week 4+:** each lane merges fixture-tested PRs independently.

## Copy the shape

`air/detectors/_example_altitude/` is a complete, trivial, passing detector
showing the whole skeleton (config → pure flag function → scoring → emit
`Detection` → `BaseDetector` subclass) and `tests/air/detectors/
test_example_altitude.py` shows the matching tests. **Copy its shape**; your
detector is the same skeleton with a harder middle.

## Rules that keep integration working

- **Import `Detection` from `contracts/`; never redefine it.** (See
  `contracts/README.md`.)
- Emit provenance and evidence on every detection — "lineage by default".
- When evidence is insufficient, **abstain** (return nothing) rather than guess.
- Detector confidence describes certainty about a *deviation* — never intent or
  threat. TCE/CAATS owns Trust; you supply evidence.
