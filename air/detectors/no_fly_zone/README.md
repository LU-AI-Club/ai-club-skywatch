# No-Fly-Zone / Airspace Violation Detector

**Team-owned. This folder is intentionally empty** — designing and building this
detector is your semester deliverable. You decide the features, thresholds, and
structure (Detector Design Card, Week 2).

**What it detects:** aircraft entering a restricted volume (a geofence with a
horizontal boundary plus altitude floor/ceiling) outside allowed conditions.
This is the air analog of the maritime risk-zone-entry detector.

## How to work this detector
1. Read [docs/DETECTOR_PLAYBOOK.md](../../../docs/DETECTOR_PLAYBOOK.md).
2. Copy the SHAPE of [air/detectors/_example_altitude](../_example_altitude).
3. Consume `AdsbObservation` from
   [air/models/observation.py](../../models/observation.py); emit `Detection`
   from `contracts/`.

## The six lanes (assign owners)
| Lane | Owns | DB? |
|------|------|-----|
| EDA + Fixtures | build zone-entry / clear-of-zone fixtures | no |
| Feature engineering | raw observations → per-aircraft position/altitude records | no |
| Baseline / reference | **the zone model** — polygon boundary + altitude band | no |
| Core detector logic | point-in-polygon + altitude test + dwell/entry | no |
| Scoring + output | confidence/severity + emit `Detection` | no |
| Evaluation + false positives | metrics; based-aircraft / emergency-squawk / transit look-alikes | no |
