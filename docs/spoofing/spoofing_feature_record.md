# SpoofingFeatureRecord

**What it does:** holds everything one consecutive pair of observations implies
about an aircraft. The contract handed from the features lane to every rule.
**File:** air/detectors/spoofing/records.py
**Inputs:** built by `build_pair_features` from two `AdsbObservation` records in
the same track segment.
**Output:** a frozen dataclass.
**How it's tested:** a valid record keeps its values; optional features default
to None; a zero or negative `dt_s` is rejected; a negative `dist_m` is
rejected; a blank `icao24` is rejected; the schema version is stamped; the
record is frozen.
**Gotchas:** optional fields are None when the inputs did not carry them. That
is normal, and a rule must abstain rather than read None as zero.

## The fields

Identity and bounds:

| Field | Meaning |
|---|---|
| `icao24` | which aircraft |
| `segment_id` | which unbroken stretch of its track |
| `prev_observed_at`, `curr_observed_at` | the two reports this came from |

What the rules actually test:

| Field | Unit | Meaning |
|---|---|---|
| `dt_s` | seconds | time between the two reports |
| `dist_m` | metres | great-circle distance between them |
| `implied_speed_kt` | knots | `dist_m / dt_s`, converted |
| `reported_speed_kt` | knots | what the aircraft claimed |
| `speed_delta_kt` | knots | implied minus reported |
| `implied_vrate_fpm` | ft/min | altitude change over `dt_s` |
| `reported_vrate_fpm` | ft/min | what the aircraft claimed |
| `vrate_delta_fpm` | ft/min | implied minus reported |
| `turn_rate_dps` | deg/s | signed; negative is a left turn |
| `agl_ft` | feet | altitude above terrain, when known |

Carried through for evidence and the identity rules: `prev_latitude`,
`prev_longitude`, `curr_latitude`, `curr_longitude`, `altitude_ft`, `nic`,
`nacp`, `callsign`.

## Two rules the record enforces itself

**`dt_s` must be positive.** A zero or negative gap means the messages arrived
out of order, and dividing by it would imply infinite speed. The record refuses
to exist rather than let that reach a rule, so `build_pair_features` must drop
such pairs instead of constructing one.

**The record is frozen.** Rules read features; nothing downstream may rewrite
them. An alert has to stay interpretable next to the numbers that produced it.

## feature_schema_version

Exposed as `air-features-v1` and stamped onto every Detection. If the fields
change in a way that breaks older rules, that string changes too, so an alert
from last week can still be read correctly.
