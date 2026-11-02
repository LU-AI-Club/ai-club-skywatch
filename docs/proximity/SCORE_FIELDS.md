# The three score fields

Every detection carries three numbers that used to be the same value three
times. They answer different questions, and TCE/CAATS reads them separately.

| Field | Question | Range | Depends on |
|---|---|---|---|
| `anomaly_score` | How far outside normal is this? | 0-1 | predicted separation only |
| `raw_model_confidence` | How sure are we, from the geometry? | 0.5-1 | lookahead time only |
| `confidence` | How sure are we, all in? | 0.15-1 | the above, discounted by reported GPS accuracy |

They move independently on purpose. A pair can be wildly anomalous and poorly
trusted (a predicted collision 110 s out between two aircraft with bad GPS), or
barely anomalous and highly trusted (a 2.9 nm pass 5 s from now).

## anomaly_score — how far outside normal

"Normal" is the loosest tier we emit: 3 nm horizontal, 900 ft vertical. A pair
predicted to pass exactly on that boundary scores **0.0**; a predicted collision
scores **1.0**.

Both dimensions must be inside a tier for the pair to fire at all, so the
binding constraint is whichever is proportionally closer to its limit:

```
anomaly = 1 - max(predicted_horizontal / 3 nm, predicted_vertical / 900 ft)
```

It deliberately ignores lookahead time. How unusual an encounter is does not
depend on how early we noticed it.

## raw_model_confidence — certainty from the geometry

Straight-line prediction degrades the further ahead it looks, so this falls
linearly from **1.0** at closest approach to **0.5** at the 120 s horizon. It
deliberately ignores how close the pair gets; certainty is not severity.

## confidence — certainty, discounted for data quality

ADS-B carries **NACp**, the 95% containment radius the aircraft reports for its
own position. We had been ignoring it. A pair whose positions could each be off
by a third of a mile cannot support a claim about a half-mile predicted miss.

The discount is taken against our tightest threshold (HIGH, 0.5 nm), using the
worse of the two aircraft, and floored at 0.3 so a detection is never discounted
to nothing:

| NACp | Position good to | Quality factor |
|---|---|---|
| 10-11 | 10 m or better | 0.99 |
| 9 | 30 m | 0.97 |
| 8 | 0.05 nm | 0.90 |
| 7 | 0.1 nm | 0.80 |
| 6 | 0.3 nm | 0.40 |
| 5 or worse | 0.5 nm or worse | 0.30 (floor) |
| not reported | treated as NACp 6 | 0.40 |

```
confidence = raw_model_confidence x position_quality
```

`position_quality` is emitted alongside the others so the discount is visible
rather than baked in silently.

## Effect on the Lynchburg hour

None on the count — it stays at 3 detections — because 99.2% of that hour
reports NACp 9 or 10. The field earns its place on worse data, not this hour.

| Severity | anomaly | confidence | raw | position quality |
|---|---|---|---|---|
| HIGH | 0.624 | 0.780 | 0.806 | 0.968 |
| LOW | 0.083 | 0.496 | 0.501 | 0.990 |
| LOW | 0.017 | 0.830 | 0.838 | 0.990 |

The two LOWs sit almost exactly on the boundary (0.08 and 0.02) while the HIGH
is well inside — which is what an anomaly score should show, and what a single
copied number could not.

## What this is not

None of these is a Trust score. We supply detector-level uncertainty and
evidence; TCE/CAATS evaluates governed Confidence, Trust and the hard gates.
`anomaly_score` says how unusual the geometry is, not how dangerous the
situation was — that depends on clearances we cannot see.

## Open

`NIC` (Navigation Integrity Category) is read and carried but not yet used.
NACp is the accuracy claim and NIC is the integrity bound on it; a pair with
high NACp but low NIC is claiming precision it cannot guarantee. Worth folding
in once there is data where the two disagree — in the Lynchburg hour 86% of
reports are NIC 8 and nothing is below 5.
