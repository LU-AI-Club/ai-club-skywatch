# Dangerous / Unusual Proximity Detector

**Team-owned. This folder is intentionally empty** — designing and building this
detector is your semester deliverable. You decide the features, thresholds, and
structure (Detector Design Card, Week 2).

**What it detects:** aircraft pairs that come within configurable horizontal,
vertical, and duration thresholds outside expected contexts. This is the air
analog of the maritime proximity/rendezvous detector, extended to 3D (add
vertical separation to horizontal distance).

## How to work this detector
1. Read [docs/DETECTOR_PLAYBOOK.md](../../../docs/DETECTOR_PLAYBOOK.md).
2. Copy the SHAPE of [air/detectors/_example_altitude](../_example_altitude).
3. Consume `AdsbObservation` from
   [air/models/observation.py](../../models/observation.py); emit `Detection`
   from `contracts/`.

## The six lanes (assign owners)
| Lane | Owns | DB? |
|------|------|-----|
| EDA + Fixtures | explore traffic; build close-pass / normal-separation fixtures | no |
| Feature engineering | time-bucket aircraft pairs; horizontal + vertical separation | no |
| Baseline / reference | expected-separation context (approach corridors, same-airport) | no |
| Core detector logic | closest-approach + threshold rule over pairs | no |
| Scoring + output | confidence/severity + emit `Detection` | no |
| Evaluation + false positives | metrics; formation flight / sequencing look-alikes | no |
