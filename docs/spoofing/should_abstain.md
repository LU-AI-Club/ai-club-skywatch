# should_abstain

**What it does:** decides whether to stay quiet instead of raising an alert.
**File:** air/detectors/spoofing/scoring.py
**Inputs:** the anomaly score, the confidence, and a `SpoofingConfig`.
**Output:** True to stay quiet, False to alert.
**How it's tested:** strong evidence alerts; thin evidence stays quiet however extreme the reading; the floor is configurable.
**Gotchas:** confidence alone decides this. A high score cannot override thin evidence, which is the entire point.

## Why a missed detection is cheaper

The repo rule is abstain rather than guess. A false alarm costs more than a
miss, because it destroys trust in every later alert - an analyst who gets bad
alerts stops reading all of them, including the right ones.
