# flag_speed_delta

**What it does:** flags a claimed ground speed that contradicts the aircraft's own positions.
**File:** air/detectors/spoofing/physics.py
**Inputs:** a `SpoofingFeatureRecord` and a `SpoofingConfig`.
**Output:** a reason string when it fires, otherwise None.
**How it's tested:** a 150 kt disagreement on a 300 kt aircraft fires; 30 kt on a 450 kt aircraft does not; the limit scales (50 for a 90 kt trainer, 150 for a 500 kt jet); a missing reported speed abstains
**Gotchas:** missing input always returns None. A rule that guesses at absent data invents detections, and the repo rule is to abstain.

## Why the limit scales

A fixed margin is wrong at both ends. 50 kt is a rounding error on a 500 kt
jet and more than half the cruise speed of a trainer, so the rule takes
whichever of the two is larger.

`speed_delta_limit_kt` is exposed separately because the event records the
limit that actually applied, not the config constant.
