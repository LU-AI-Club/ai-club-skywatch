# flag_teleport

**What it does:** flags movement faster than any aircraft can manage over the ground.
**File:** air/detectors/spoofing/physics.py
**Inputs:** a `SpoofingFeatureRecord` and a `SpoofingConfig`.
**Output:** a reason string when it fires, otherwise None.
**How it's tested:** an impossible speed fires; a 780 kt jet stream tailwind does not; exactly at the limit does not (the rule is 'greater than'); a missing speed abstains; a sub-half-second gap abstains
**Gotchas:** missing input always returns None. A rule that guesses at absent data invents detections, and the repo rule is to abstain.

## Why the limit is so high

Airliners genuinely reach 750-800 kt over the ground with a strong tailwind,
so a limit near cruise speed would flag honest traffic all day. A fabricated
position typically implies thousands to tens of thousands of knots, so nothing
real is lost by setting the gate at 1000.
