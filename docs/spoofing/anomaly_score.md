# anomaly_score

**What it does:** measures how far past the limit a value went, from 0.0 to 1.0.
**File:** air/detectors/spoofing/scoring.py
**Inputs:** the measured value, the threshold it broke, and an optional margin.
**Output:** a float from 0.0 to 1.0.
**How it's tested:** exactly at the limit scores 0.5; a 10% overshoot scores 0.55; a wild overshoot saturates at 1.0; under the limit never exceeds 0.5; the sign does not matter; a gate with nothing to measure returns the nominal score.
**Gotchas:** scores carry three decimals, so a one-knot overshoot on a 1000 kt limit rounds back to 0.5. That is intended - such a margin is not meaningfully anomalous.

## The shape

0.5 at the threshold, rising to 1.0 a full margin beyond, saturating there.
An aircraft at 1,001 kt is barely over the line; one at 21,000 kt is wildly
over; this is the number that tells them apart. Copied from
`altitude_confidence` in the reference detector.

## Gates with no number

`identity_drift_v1` is a yes or no, with no quantity attached. It scores
`UNMEASURED_SCORE` (0.6): it fired, so it is not zero, but we cannot say how
far past the line it went.
