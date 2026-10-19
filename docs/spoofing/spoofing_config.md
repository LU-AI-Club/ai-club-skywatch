# SpoofingConfig

**What it does:** holds every limit the detector uses, in one place.
**File:** air/detectors/spoofing/config.py
**Inputs:** none - a frozen dataclass of defaults, any of which can be overridden.
**Output:** a settings object every rule reads from.
**How it's tested:** the agreed defaults are present; a threshold can be overridden; the object is frozen; a non-positive threshold, an out-of-range fraction, an impossible confidence floor and a gap limit below the pair spacing are all rejected.
**Gotchas:** no rule may hard-code a number. A literal inside a rule cannot be swept by the evaluation lane and will not appear on the alert.

## The limits

| Setting | Default | Why |
|---|---|---|
| `teleport_kt` | 1000 | Airliners reach 750-800 kt in a jet stream; fabricated positions imply thousands |
| `turn_rate_dps` | 10 | A standard rate turn is 3 deg/s |
| `speed_delta_kt` | 50 | Floor for the speed-disagreement margin |
| `speed_delta_frac` | 0.30 | ...or 30% of reported speed, whichever is larger |
| `vrate_delta_fpm` | 2000 | Above baro noise; a normal climb is 1500-2500 |
| `altitude_quantum_ft` | 25 | The step size altitude is reported in |
| `nic_floor` | 1 | Integrity at or below this is "I do not trust my position" |
| `nic_min_duration_s` | 30 | Brief dips are ordinary equipment behaviour |
| `pingpong_reversals` | 3 | Direction flips before it reads as two transmitters |
| `max_gap_s` | 60 | Silence longer than this splits a track |
| `min_dt_s` | 0.5 | Below this, timestamp error dominates |
| `min_confidence` | 0.35 | Below this, abstain |

A fixed speed margin alone is wrong for both a 90 kt trainer and a 500 kt jet,
which is why that one rule takes the larger of two values.

## altitude_quantum_ft

The feed rounds altitude to 25 ft, so a level aircraft appears to jump a whole
step at a time. Over a short gap that implies a large climb rate purely as an
artefact. `flag_vrate_delta` subtracts that bound before comparing; without
it, 96% of all alerts on an hour of real data were level aircraft.

If the club antenna reports altitude at a different resolution, this is the
one number to change.
