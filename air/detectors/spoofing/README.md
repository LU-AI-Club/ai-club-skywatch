# Spoofing / Position-Inconsistency Detector

**Team-owned. This folder is intentionally empty** — designing and building this
detector is your semester deliverable. Do not expect stub code to fill in; you
decide the features, thresholds, and structure (that is the Detector Design
Card work in Week 2).

**What it detects:** ADS-B reports that are physically implausible — impossible
position jumps, kinematic contradictions (reported speed/track vs. what the
positions imply), or degraded navigation-integrity fields (NIC/NACp).

## How to work this detector
1. Read [docs/DETECTOR_PLAYBOOK.md](../../../docs/DETECTOR_PLAYBOOK.md) — the six
   lanes, the "definition of done", and how to work in parallel.
2. Read the worked reference [air/detectors/_example_altitude](../_example_altitude).
   Copy its **shape**, not its logic.
3. Consume the shared input contract
   [air/models/observation.py](../../models/observation.py) (`AdsbObservation`).
4. Emit the shared output contract: the `Detection` from `contracts/`
   (import it, never redefine it).

## The six lanes (assign owners in your team)
| Lane | Owns | DB? |
|------|------|-----|
| EDA + Fixtures | explore ADS-B; build positive/negative fixtures | no |
| Feature engineering | raw observations → your feature-record dataclass | no |
| Baseline / reference | the feasible physics envelope ("what is possible") | no |
| Core detector logic | the flag rule (pure functions over features) | no |
| Scoring + output | confidence/severity + emit `Detection` | no |
| Evaluation + false positives | metrics, threshold sweep, benign look-alikes | no |

Suggested files once you start: `config.py`, `features.py`, `logic.py`,
`scoring.py`, `detector.py` — but the layout is yours to decide.
