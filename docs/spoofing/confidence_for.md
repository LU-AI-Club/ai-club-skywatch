# confidence_for

**What it does:** measures how much the evidence behind an event can be trusted.
**File:** air/detectors/spoofing/scoring.py
**Inputs:** a `SpoofingEvent` and a `SpoofingConfig`.
**Output:** a float from 0.0 to 1.0.
**How it's tested:** good evidence scores 1.0; a very short time gap lowers it; a thin segment lowers it; a gate with no measurement lowers it; the result always stays within bounds.
**Gotchas:** this is a different question from `anomaly_score`, and conflating the two is the easiest mistake in the detector.

## Score versus confidence

*Score* is how weird. *Confidence* is how sure we are it is really weird.

"This aircraft did 20,000 kt, but I had two sparse reports to go on" is high
score and low confidence - and the right response is silence, which is what
`should_abstain` does with it.

## What lowers it

| Condition | Why |
|---|---|
| A very short time gap | Timestamp error dominates the arithmetic |
| A thin segment | Too few reports to establish a pattern |
| No measurement | A yes/no gate carries less information |

Deliberately conservative. A detector that is loudly wrong is worse than one
that stays quiet, because an analyst who gets bad alerts stops reading them.
