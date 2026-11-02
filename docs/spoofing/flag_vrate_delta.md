# flag_vrate_delta

**What it does:** flags a claimed climb rate that contradicts the altitude change.
**File:** air/detectors/spoofing/physics.py
**Inputs:** a `SpoofingFeatureRecord` and a `SpoofingConfig`.
**Output:** a reason string when it fires, otherwise None.
**How it's tested:** a claimed 3500 fpm climb with no altitude change fires; a legal steep descent where the altitudes agree does not; a missing altitude abstains; the 25 ft altitude step artefact is ignored; a real disagreement at a short gap still fires; the allowance shrinks as the gap grows; a modest disagreement over a long gap fires
**Gotchas:** missing input always returns None. A rule that guesses at absent data invents detections, and the repo rule is to abstain.

## Same idea, one axis up

The aircraft reports a vertical rate, and its own altitudes imply another. A
large disagreement means one of the two is invented. The threshold sits above
barometric noise and sensor lag - a normal climb is 1500-2500 fpm, so an
honest aircraft never approaches it.

## The altitude quantisation allowance

Altitude is reported in fixed 25 ft steps, so a level aircraft still appears
to jump a whole step at a time. Over a short gap that implies a large phantom
climb rate:

    25 ft over 0.55 s  ->  2,727 fpm, on an aircraft flying level

39% of all pairs in `data/lynchburg_adsb.csv` are under two seconds apart, so
before this was accounted for the rule produced **16,953 of 17,733 alerts** on
one hour of real data -- almost every one a level aircraft.

`vrate_quantisation_fpm` returns the bound that artefact can reach (two steps,
since either endpoint may be rounded) and the rule subtracts it before
comparing. The allowance shrinks as the gap grows, which is correct: a longer
gap is more trustworthy.

| Gap | Allowance |
|---|---|
| 1 s | 3,000 fpm |
| 10 s | 300 fpm |
| 60 s | 50 fpm |

Widening the threshold instead would have been the wrong fix: it would hide
genuine disagreements at long gaps, where the measurement is most reliable.

After the change the real hour produced **981 alerts rather than 17,756**, and
every positive fixture still fires.
