# flag_pingpong

**What it does:** Flags an aircraft whose track bounces back and forth between two places with every hop physically impossible, the signature of two transmitters sharing one id.

**File:** air/detectors/spoofing/identity.py

**Inputs:**
- `records`: a sequence of feature records from one aircraft, as dicts or objects. Each needs `lat` (degrees), `lon` (degrees) and `timestamp` (seconds, or a `datetime`). They are sorted by timestamp inside the function.
- `config`: a `SpoofingConfig`. The function reads these fields and falls back to the defaults if one is missing:
  - `max_speed_mps` (meters/second, default 450): a hop faster than this is impossible.
  - `pingpong_min_hops` (count, default 3): how many impossible, direction-flipping hops in a row are needed to fire.
  - `pingpong_reversal_tolerance_deg` (degrees, default 45): how close to a 180° turn counts as a flip.
  - `pingpong_min_hop_distance_m` (meters, default 1): the smallest jump that counts as a different position when two records share a timestamp.

**Output:** `str | None`. A reason string if it fires, otherwise `None`. The string gives the number of hops, the average hop distance (km), and the peak implied speed (m/s) against the limit.

**How it's tested:**
- It fires on a track that goes A, B, A, B, which is exactly 3 impossible hops, and on longer bouncing.
- It fires if the bouncing starts after normal flight or is followed by stationary points.
- It still fires on shuffled input, `datetime` timestamps, object records, and two places at the same timestamp.
- It stays quiet for a single bad position (out and back is only 2 hops) and a one-way teleport.
- It stays quiet for a normal flight, impossible hops that never reverse (a staircase of 90° turns), and the same position at the same timestamp.
- It stays quiet if a plausible hop breaks the run, and for fewer than 4 records.
- The config changes behave as expected:
  - Raising or lowering `pingpong_min_hops` changes when it fires.
  - Raising `max_speed_mps` or spacing the records further apart in time makes the hops plausible, so it stays quiet.
  - The reversal tolerance decides whether an imperfect return counts as a flip.
  - An empty config uses the defaults.
- The input list is not modified.

**Gotchas:**
- Altitude is ignored. Speed and direction are 2D only.
- It assumes all records are from one aircraft. Grouping by id is up to the caller.
- A single plausible hop in the middle of a bounce resets the run, so a dropped or lucky in-between packet can hide a real ping-pong.
- If records are far apart in time, the hops can look plausible and it won't fire.
- Two transmitters close enough that the jump stays under `max_speed_mps` won't be caught.
- A missing or `None` lat, lon or timestamp raises an error. It doesn't skip the record.
- Hops across the ±180° longitude line may be misjudged. Distance handles it, but the direction check does not wrap.
- It returns on the first qualifying run and doesn't report later ones.
- The config field names are my assumption. They need to match the real `SpoofingConfig`.