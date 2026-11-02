# build_evidence

**What it does:** attaches the observations that prove a finding.
**File:** air/detectors/spoofing/emit.py
**Inputs:** a `SpoofingEvent`.
**Output:** a list of `Evidence` objects from the platform contract.
**How it's tested:** the evidence carries the arithmetic in its metadata; an event with no feature records still produces one evidence item.
**Gotchas:** identity findings may rest on whole tracks rather than one pair, so the function must not assume a feature record exists.

## Why the arithmetic travels with it

Each item carries `dt_s`, `dist_m`, the implied and reported speeds, and the
feature schema version. A reader can redo the maths from the alert alone,
without the original data in hand. That is what separates a detection from an
assertion.
