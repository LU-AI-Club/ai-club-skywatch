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

| Lane | Owns |
|------|------|
| 1. EDA + Fixtures | explore the data; build positive/negative fixture files everyone tests against |
| 2. Feature engineering | raw `AdsbObservation` → your feature-record dataclass |
| 3. Baseline / reference | defines & versions "normal" (envelopes, zones, corridors) |
| 4. Core detector logic | the flag rule — pure functions over feature records |
| 5. Scoring + output | confidence/severity + emit the `Detection` contract |
| 6. Evaluation + false positives | metrics, threshold sweeps, benign look-alikes |

The Technical Lead (and Xenith) own the DB, the live normalizer, and TCE/CAATS
wiring — **not** the detector teams.

## Definition of done (every task)

> A merged pull request containing the function **plus a `pytest` test that runs
> on a fixture — no database, no services.**

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
