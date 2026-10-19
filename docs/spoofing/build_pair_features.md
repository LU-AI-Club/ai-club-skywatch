# build_pair_features

**What it does:** works out what one consecutive pair of reports implies about an aircraft.
**File:** air/detectors/spoofing/features.py
**Inputs:** two `AdsbObservation` records and a `segment_id`.
**Output:** a `SpoofingFeatureRecord`, or None if the pair cannot be used.
**How it's tested:** a pair yields the arithmetic (one degree of latitude over 60 s is about 3,601 kt); claimed and derived speed are both kept; climb rate comes from the altitudes; turn rate is signed and wrapped; a non-positive time gap is dropped; two different aircraft are never paired; missing optional fields stay None.
**Gotchas:** returns None rather than raising. A zero or negative gap means the reports arrived out of order, and dividing by it would imply infinite speed.

## The arithmetic

| Value | How |
|---|---|
| `dt_s` | difference of the two timestamps |
| `dist_m` | haversine over the two positions |
| `implied_speed_kt` | `dist_m / dt_s`, converted at 1.943844 |
| `speed_delta_kt` | implied minus what the aircraft claimed |
| `implied_vrate_fpm` | altitude change over `dt_s / 60` |
| `vrate_delta_fpm` | implied minus claimed |
| `turn_rate_dps` | wrapped heading change over `dt_s` |

That last comparison is the whole detector in one line: what the aircraft
*claims* against what its own positions *imply*.
