# severity_for

**What it does:** decides how loud the alarm should be, from which rule fired.
**File:** air/detectors/spoofing/scoring.py
**Inputs:** the gate name, e.g. `teleport_v1`.
**Output:** a `SeverityLevel` - HIGH, MEDIUM or LOW.
**How it's tested:** each tier maps as agreed; an unknown gate returns LOW rather than raising.
**Gotchas:** an unknown gate is LOW, not an error. A new rule must not be able to crash the pipeline on its first run.

## The tiers

| Severity | Gates | Why |
|---|---|---|
| HIGH | teleport, turn rate, subterrain, coexistence, ping-pong | Limits sit beyond the possible, so a hit means something is genuinely wrong |
| MEDIUM | speed delta, vrate delta, reappearance, registry mismatch | Claimed and derived values disagreeing has innocent explanations |
| LOW | nic floor, identity drift | A single soft indicator |
