# build_provenance

**What it does:** records what produced an alert and under which settings.
**File:** air/detectors/spoofing/emit.py
**Inputs:** a `SpoofingEvent` and a `SpoofingConfig`.
**Output:** a `ProvenanceRecord` from the platform contract.
**How it's tested:** the settings that actually applied are recorded, not the defaults; the processing step names the gate that fired.
**Gotchas:** the whole config travels with every detection, not just the one threshold that was crossed.

## Why the whole config

A detection is only interpretable next to the limits that produced it. Change
a threshold next week and yesterday's alerts must still say what they were
measured against. Recording only the crossed threshold would leave the rest
unknowable.
