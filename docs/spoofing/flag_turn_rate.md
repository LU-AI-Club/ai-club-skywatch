# flag_turn_rate

**What it does:** flags a turn sharper than an airframe can fly.
**File:** air/detectors/spoofing/physics.py
**Inputs:** a `SpoofingFeatureRecord` and a `SpoofingConfig`.
**Output:** a reason string when it fires, otherwise None.
**How it's tested:** an aerobatic turn fires; the same turn to the left fires too; a standard rate turn does not; a missing heading abstains
**Gotchas:** missing input always returns None. A rule that guesses at absent data invents detections, and the repo rule is to abstain.

## Signed in, magnitude out

Turn rate is signed on the feature record - negative is a left turn - so the
rule compares `abs(...)`. The event then stores the magnitude, since
`measured` is always positive by the agreed contract.
