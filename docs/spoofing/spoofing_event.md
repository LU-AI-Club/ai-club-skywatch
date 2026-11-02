# SpoofingEvent

**What it does:** carries one rule hit from the rules to the scoring lane.
**File:** air/detectors/spoofing/records.py
**Inputs:** built by a physics or identity rule when it fires.
**Output:** a frozen dataclass.
**How it's tested:** a valid event keeps its values; blank `gate`,
`detection_type` or `reason` is rejected; an empty aircraft list is rejected; a
backwards time window is rejected; `identity_drift_v1` is allowed to carry no
measurement; an identity finding may name several aircraft.
**Gotchas:** an event carries **no score and no severity**. Those are computed
later from `measured` against `threshold`, so a rule never decides how loud its
own alarm is.

## The fields

| Field | Meaning |
|---|---|
| `gate` | which rule fired, e.g. `teleport_v1` |
| `detection_type` | the family of finding, e.g. `position_jump` |
| `reason` | short constant, e.g. `TELEPORT` |
| `icao24s` | the aircraft involved; more than one for identity findings |
| `observed_from`, `observed_to` | the evidence window |
| `measured` | the value that broke the rule |
| `threshold` | the limit it broke |
| `unit` | `kt`, `fpm`, `deg/s`, `nm`, `ft`, `nic` or `count` |
| `latitude`, `longitude`, `altitude_ft` | where to put it on a map |
| `features` | the records that prove it |
| `details` | a few extra values for the alert text |

## The agreed gate table

Every rule writes these exact strings. Scoring matches on them.

| gate | reason | detection_type | measured | threshold | unit |
|---|---|---|---|---|---|
| `teleport_v1` | `TELEPORT` | `position_jump` | implied speed | `cfg.teleport_kt` | `kt` |
| `turn_rate_v1` | `IMPOSSIBLE_TURN` | `kinematic_inconsistency` | abs turn rate | `cfg.turn_rate_dps` | `deg/s` |
| `speed_delta_v1` | `SPEED_DISAGREEMENT` | `kinematic_inconsistency` | abs speed delta | the computed limit | `kt` |
| `vrate_delta_v1` | `VRATE_DISAGREEMENT` | `kinematic_inconsistency` | abs climb delta | `cfg.vrate_delta_fpm` | `fpm` |
| `nic_floor_v1` | `INTEGRITY_FLOOR` | `integrity_degraded` | seconds held at the floor | `cfg.nic_min_duration_s` | `s` |
| `subterrain_v1` | `BELOW_TERRAIN` | `position_implausible` | depth below ground | `0` | `ft` |
| `coexistence_v1` | `IDENTITY_COEXISTENCE` | `identity_coexistence` | None | None | None |
| `pingpong_v1` | `PING_PONG` | `identity_coexistence` | None | None | None |
| `reappear_v1` | `IMPOSSIBLE_REAPPEARANCE` | `position_jump` | distance from last position | reachable distance | `nm` |
| `registry_mismatch_v1` | `REGISTRY_MISMATCH` | `identity_mismatch` | observed speed | registry max speed | `kt` |
| `identity_drift_v1` | `IDENTITY_DRIFT` | `identity_mismatch` | None | None | None |

Three conventions that go with it:

- **`measured` is always positive.** Turn rate is signed in the feature record;
  the event stores its absolute value. `subterrain_v1` stores depth below
  ground as a positive number, so 300.0 means 300 ft underground.
- **For `speed_delta_v1`, `threshold` is the effective limit** - the larger of
  50 kt and 30% of reported speed - not the config constant. Otherwise the
  alert shows a limit that was not the one applied.
- **Three gates carry no numbers:** `identity_drift_v1`, `coexistence_v1` and
  `pingpong_v1`. The last two could in principle report a separation or a
  reversal count, but their rules return only a reason string and recovering
  the figure would mean duplicating their logic. A fabricated value would
  score as though it had been measured, so they are left unmeasured and take
  the nominal score. Scoring must handle None without crashing.
- **`nic_floor_v1` measures duration, not the NIC value.** Integrity is
  lower-is-worse while scoring assumes higher-is-worse, so scoring the NIC
  itself made a total collapse (NIC 0) score *lower* than a mild dip. How long
  it stayed down is the quantity that grows with severity, and it is what the
  rule triggers on. The lowest NIC seen is kept in `details`.

## details keys

Values are strings, numbers or booleans - nothing nested. Every event carries
`segment_id` and `observation_count`. Then per gate:

| Gate | Extra keys |
|---|---|
| `nic_floor_v1` | `lowest_nic` |
| `coexistence_v1`, `reappear_v1` | `gap_s`, `reachable_nm` |
| `coexistence_v1`, `pingpong_v1` | `finding` (the rule's reason string) |
| `registry_mismatch_v1` | `registry_model`, `registry_max_speed_kt` |
| `identity_drift_v1` | `callsigns` |

Scoring may read `segment_id` and `observation_count`. Everything else is for
the alert text only - scoring must never depend on a gate-specific key.
