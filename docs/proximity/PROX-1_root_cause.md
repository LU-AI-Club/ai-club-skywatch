# PROX-1 root-cause note: we flag aircraft that are tens of miles apart

**Found.** `flag_pair` trusted any pair with `0 < t_cpa <= 120 s`, however far apart
they were. Fast head-on closers (~900 kt) cover 30 nm in 120 s, so pairs up to
31.8 nm apart passed the gate, and 265 of 1,128 detections had the pair more than
10 nm apart. The prediction assumes both aircraft hold speed and track, and that
assumption gets worse the further ahead it looks.

**Evidence (Lynchburg hour).** I predicted each aircraft's position from one report
using its ground speed and track, then compared it with where it actually was
after 30 to 120 s (about 215k to 255k samples per horizon, airborne only):

| Lookahead | median miss | p90 miss | p99 miss |
|---|---|---|---|
| 30 s | 0.03 nm | 0.48 nm | 1.15 nm |
| 60 s | 0.13 nm | 1.60 nm | 3.58 nm |
| 90 s | 0.31 nm | 3.22 nm | 6.65 nm |
| 120 s | 0.65 nm | 5.19 nm | 10.09 nm |

That is per aircraft, and a pair's error is bigger. At 120 s the p90 miss is about
as large as the 5 nm INFO limit and ten times the 0.5 nm HIGH limit, so a
"0.02 nm predicted miss" from 30 nm out is noise. This includes turning terminal
traffic, which is the point: real traffic turns.

**Fix.** New config value `max_current_separation_nm: 10.0` and a gate in
`flag_pair`: drop the pair if it is currently more than 10 nm apart. It is a hard
gate rather than lower confidence, because confidence already falls with `t_cpa`
and the far pairs still came out as detections. A pair 10 nm apart closing at
~900 kt reaches closest approach in about 40 s, where the p90 miss is about 0.5 to
1 nm, which is close to the MEDIUM/HIGH limits.

**Result.** The Lynchburg replay goes from 1,128 to 898 detections, and the largest
current separation is now 10.0 nm instead of 31.8 nm. The new
`proximity_far_converging` fixture (25 nm apart now) fired HIGH before the change
and fires nothing after. `proximity_near_term` (5 nm apart now) still fires HIGH.

**Left alone.** `max_tcpa_s` (120 s) is unchanged. The 1,000 ft vertical flood is
PROX-2, the severity floor is PROX-3, and turning traffic is PROX-4. The 10 nm
value is a judgement from one hour of data and should be rechecked against more.
