# PROX-6 root-cause note: almost everything we flag is terminal-area traffic

**Found.** After PROX-1 and PROX-2 the Lynchburg hour still produced 722 detections
over 361 aircraft pairs. 338 of those 354 flagged pairs — **95%** — had at least one
aircraft below 5,000 ft, and every one of the 20 HIGH-severity pairs was 130–170 nm
from Lynchburg, which puts them in the terminal areas of Charlotte, Raleigh-Durham
and the DC-area fields. The detector was not finding dangerous encounters. It was
finding airports.

**Evidence (Lynchburg hour, flagged pairs only).**

| Statistic | p10 | median | p90 |
|---|---|---|---|
| Pair altitude | 398 ft | 2,818 ft | 4,806 ft |
| Slower aircraft's ground speed | 62 kt | 169 kt | 208 kt |
| Closure rate | 5 kt | 124 kt | 364 kt |

40% of pairs were below 2,000 ft and 26% below 1,000 ft. 30% had both aircraft
under 150 kt and 21% were closing at under 30 kt. That is pattern work, approach,
departure and rotary traffic — aircraft that are close deliberately.

Detections by altitude band:

| Altitude | INFO | LOW | MED | HIGH | Total |
|---|---|---|---|---|---|
| < 5,000 ft | 319 | 213 | 114 | 32 | **678** |
| 5–10,000 ft | 25 | 3 | 1 | 0 | 29 |
| 10–30,000 ft | 7 | 0 | 0 | 0 | 7 |
| 30,000 ft + | 6 | 1 | 0 | 1 | 8 |

Cruise altitude produced 8 detections in an hour. Terminal airspace produced 678.

**Why thresholds cannot fix this.** The real low-altitude HIGH detections have
predicted separations of 0.00–0.41 nm and 47–383 ft. The synthetic head-on fixture
we demo with is 0.20 nm and 200 ft. They occupy the same range, so any threshold
tight enough to silence the terminal noise also silences a genuine collision course.
Altitude is what separates them, not distance.

**Approach sequencing alone does not explain it either.** A "both descending,
tracks within 20°, below 10,000 ft" rule suppressed only 13 of 366 pairs (3.6%).
These are not neat landing queues — they are mixed, maneuvering terminal traffic.
A narrow sequencing rule would have been the wrong fix.

**Fix.** New config value `min_altitude_ft: 5000` and a gate in `flag_pair`: drop
the pair if either aircraft is below it. The justification is not that terminal
traffic is unimportant — it is that this detector cannot judge it. Below 5,000 ft
the separation standards differ, traffic is maneuvering in ways a constant-track
prediction cannot follow, and "close" is routine. Doing it properly needs airport
and runway context (FAA NASR) that we have not sourced yet.

**Result.** The Lynchburg replay goes from 722 detections over 361 pairs to
**28 detections over 22 pairs**, and from 33 HIGH to 1. The one remaining HIGH is
`ad2862/c02e9b` at FL345/FL360, predicted 0.15 nm and 339 ft apart, closing at
768 kt — a head-on at cruise, which is exactly what this detector is for. Two new
fixtures lock the boundary: `proximity_terminal_altitude` (the head-on geometry at
3,000 ft, expects nothing) and `proximity_just_above_floor` (the same at 5,200 ft,
still HIGH).

**Left alone.** `max_tcpa_s`, the severity tiers and the ground check are
unchanged. The double-counting is PROX-5, the severity floor is PROX-3, and
modelling turning traffic is PROX-4 — the last of which is the real path back to
covering terminal airspace instead of excluding it.

**Caveat.** 5,000 ft is MSL, not above ground. Field elevations in this coverage
area run from sea level to about 2,900 ft, so the effective height above ground
varies. Per-airport elevations from FAA NASR would make this exact rather than
approximate. The number also comes from one hour over one region and should be
rechecked on more data.

---

**Also fixed here:** `scripts/make_proximity_fixtures.py` would not run. The
`proximity_spans_window` entry lost its closing brace when PROX-5 was merged, so
the file was a syntax error. Nothing caught it because the generated fixtures were
already committed and no test executes the generator. Worth adding one that does.
