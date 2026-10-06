# flag_reappearance

**What it does:** Flags an aircraft that reappears after a gap somewhere it could not have reached in that time at its maximum speed.

**File:** air/detectors/spoofing/identity.py

**Inputs:**
- `last_before`: dict or object, the last observation before the gap. Needs `lat` (degrees), `lon` (degrees) and `timestamp` (seconds, or a `datetime`).
- `first_after`: dict or object, the first observation after the gap. Same fields as `last_before`.
- `config`: a `SpoofingConfig`. The function reads these fields and falls back to the default if one is missing:
  - `max_speed_mps` (meters/second, default 450): the fastest the aircraft can fly.
  - `reappearance_margin_m` (meters, default 0): extra slack added to the reachable radius, for position error.

**Output:** `str | None`. A reason string if it fires, otherwise `None`. The string gives the distance from the last known position (km), the gap length (s), and the maximum reachable distance (km) at the speed limit.

Example: `reappearance: returned 175.2 km from last position after a 60 s gap; at most 27.0 km reachable at 450 m/s`

**How it's tested:**
- It fires when the aircraft reappears outside the circle, in any direction.
- The reason string mentions the gap length and the speed limit.
- It works with `datetime` timestamps and with object records as well as dicts.
- It stays quiet when the reappearance is inside the circle, when the gap is very long (anywhere is reachable), and when the aircraft comes back in the same position.
- At the boundary, a gap just long enough stays quiet and one just too short fires.
- A zero or negative gap is not a gap, so it returns `None`.
- A higher `max_speed_mps` widens the circle and a lower one shrinks it.
- The margin extends the circle.
- An empty config uses the defaults.
- The input records are not modified.

**Gotchas:**
- The circle is a straight line on the ground. Altitude is ignored.
- It can't catch an impostor who reappears inside the circle.
- A very long gap makes almost anywhere reachable, so it goes quiet by design.
- There is no minimum gap length. The caller decides what counts as a gap, and the function judges any pair it is given.
- A gap of zero or less returns `None`. Duplicate or out-of-order timestamps are for the caller to handle.
- A missing or `None` lat, lon or timestamp raises an error.
- The config field names are my assumption. They need to match the real `SpoofingConfig`.