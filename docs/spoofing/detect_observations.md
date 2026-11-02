# detect_observations

**What it does:** runs every stage of the detector over a list of observations.
**File:** air/detectors/spoofing/detector.py
**Inputs:** a list of `AdsbObservation`.
**Output:** a list of `Detection`. Empty for now.
**How it's tested:** an empty list produces nothing; the 40-point
`clean_track.json` fixture runs without raising and produces nothing; the
teleport fixture also runs without raising.
**Gotchas:** it returns no detections at all today, on purpose. The feature,
rule, scoring and emit stages are not merged yet, and the repo rule is to
abstain rather than guess.

## The stages, in order

| Stage | Owner | Lands in |
|---|---|---|
| 1. Features | Christopher, Isabella | `features.py` |
| 2. Physics rules | Henry, Silas | `physics.py` |
| 3. Identity rules | Ryan, Ian | `identity.py` |
| 4. Scoring | Daniel | `scoring.py` |
| 5. Emit | Isabella | `emit.py` |

## Why wire it before the stages exist

Nothing can be judged yet, so this could have waited. Building it now means the
pipeline runs end to end from a clean checkout, which gives every lane
something real to plug into and proves the platform contract is satisfied
before there is any logic to argue about.

The clean-track test also keeps earning its keep: once the rules land, a normal
flight must *still* produce nothing, which is exactly the false-alarm check.
