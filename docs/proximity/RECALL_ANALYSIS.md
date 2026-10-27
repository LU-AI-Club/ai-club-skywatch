# Are we too strict? Recall against scripted collisions

**2026-10-27.** PROX-1, 2, 3 and 8 took the Lynchburg hour from 1,128 detections
to 3. Every one of those cuts was justified against real traffic — but all of
them measured *precision* (are the things we emit worth emitting?). None measured
*recall* (would we still catch a real one?).

So: ten scripted collisions — two aircraft arriving at the same point at the same
instant — run through the detector as it stands. Tests live in
`tests/air/detectors/proximity/test_proximity_recall.py`.

## What we catch

| Scenario | Result |
|---|---|
| Head-on, FL350, 900 kt closure | HIGH |
| Head-on, 10,000 ft, 900 / 500 / 220 kt closure | HIGH |
| Right-angle crossing, FL300 | HIGH |
| Overtaking (480 vs 380 kt, same heading) | HIGH |
| Head-on at 5,100 ft, just above the floor | HIGH |

Every collision above 5,000 ft is caught, at every closure rate and geometry
tested, and always as HIGH. The tuning did not break the core detector.

## Three blind spots

### 1. Nothing below 5,000 ft is visible at all

`min_altitude_ft: 5000` (PROX-8) suppresses every pair with an aircraft below it.
A deliberate head-on collision at 3,000 ft, at 4,000 ft, or at 1,500 ft in the
pattern produces **no detection, ever** — not late, not low-severity, nothing.

This is the uncomfortable one, because low altitude near airports is exactly
where real midair collisions happen. PROX-8 bought a 95% cut in noise by
declaring terminal airspace out of scope. That is defensible as a stated scope
limit; it is not defensible if anyone believes the detector covers that airspace.

**It must be said out loud in the demo:** this detector covers en route traffic
above 5,000 ft. Terminal-area proximity needs airport and runway context
(FAA NASR) and the maneuvering model from PROX-4.

### 2. Pure vertical convergence is invisible

Two aircraft on the same track at the same speed, one climbing into the other.
Horizontally they never move relative to one another, so relative velocity is
~0, `time_to_cpa` returns `None`, and the pair is dropped before any threshold
is consulted.

This is a bug, not a tuning choice. `t_cpa` is derived from horizontal motion
only; the vertical dimension is extrapolated to that time but never drives it.
A level-off error — an aircraft climbing through an occupied flight level
directly beneath traffic — is a real conflict shape and we cannot see it.

### 3. Warning time shrinks as closure rate rises

| Closure rate | First alert before impact |
|---|---|
| 220 kt | 120 s |
| 500 kt | 72 s |
| 900 kt | **40 s** |

`max_current_separation_nm: 10` (PROX-1) is the cause: a pair closing at 900 kt
covers 10 nm in 40 seconds, so they are outside the gate until then. The faster
the encounter, the less warning we give — which is backwards from what you want.

PROX-1 was the right call on the evidence (prediction error at 120 s is larger
than the thresholds themselves), but a fixed distance gate is the wrong shape.
A **time-based** gate would behave correctly: "ignore the pair until closest
approach is within N seconds", which gives the same filtering at every speed.
Worth raising as a follow-up ticket.

## What this means

The detector is **correctly calibrated for what it now claims to cover** —
en route traffic above 5,000 ft, with horizontal relative motion — and the 3
remaining Lynchburg detections are believable rather than an artifact of
over-tuning.

It is **not** a general-purpose collision detector, and three things should be
stated plainly rather than discovered by a reviewer:

1. Below 5,000 ft we report nothing.
2. Pure vertical convergence is not modelled.
3. At airline closure speeds the warning is about 40 seconds.

All three are now pinned by tests, so if someone fixes one the suite will tell
them.
