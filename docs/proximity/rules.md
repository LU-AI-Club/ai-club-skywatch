# <function name>

**Author:** <you> · **PR:** #<number> · **File:** `air/detectors/proximity/<file>.py`

## What it does
*Two or three sentences, plain English. What goes in, what comes out, and why
the pipeline needs it. Someone who has not read the code should follow this.*

severity_for and flag_pair act as the rulebook for the proximity detector: they decide whether a pair of aircraft is a real safety concern, and if so, how serious. 
severity_for looks up how close is "too close" in a table, from strictly tight to strictly close, and returns a rating like HIGH, MEDIUM, LOW, INFO, or nothing at all if they're not close enough to worry about. 
flag_pair first checks the prediction is even trustworthy — are they actually flying toward each other, and is that closest approach coming up soon enough to believe? If yes, it hands the predicted distance to severity_for.


## Inputs and outputs
| | Type | Units | Notes |
|---|---|---|---|
| in | | | |
| out | | | |

in predicted_horizontal_nm, predicted_vertical_ft (severity_for)	nautical miles, feet	Predicted separation at closest approach
in	geom: PairGeometry (flag_pair)	—	Pair's relative motion state (t_cpa_s, converging, predicted separations)
in	cfg: ProximityConfig (both)	—	Tier table and max_tcpa_s, loaded from configs/detectors/proximity.yaml
out	SeverityLevel | None	—	Outputs one of HIGH, MEDIUM, LOW, INFO, ranked tightest to loosest; None means "do not emit detection"

## How it works
*The approach in 3-5 bullets or a short numbered list. Include the formula if
there is one. Not a line-by-line reading of the code — the reasoning.*

severity_for sorts cfg.tiers tightest-first (by max_horizontal_nm, max_vertical_ft) so the lookup order doesn't depend on how the YAML happens to list them 
It walks the sorted tiers and returns the first on wehre both hold: predicted_horixontal_nm < tier.max_horizontal_nm and predicted_vertical_ft < tier.max_vertical_ft. Both axes must be tight - being close on only one doesn't count
if no tier matches on both axes it returns None
flag_pair runs a chain of gates, in order, bailingh out to None the moment one fials: no relative velocity (t_cpa_s is None) -> not converging -> closest approach too far in teh future (t_cpa_s > cfg.max_tcpa_s) -> missing predicted separations.
only if every gate passes does it hadn the predicted separations to severity_for and return whatever comes back

## Decisions and trade-offs
*Anything you chose that a reader might question. Example: "I skip ticks across
gaps longer than 30 s rather than interpolating, because inventing a position
across a 2-minute silence would create conflicts that never happened."*

severity_for sorts cfg.tiers itself rather than trusting the YAML's listed order. The docstring says the config is already tightest-first, but the function doesn't rely on that holding — a small sort cost per call buys safety against a future config edit breaking the order.
Every threshold (max_tcpa_s, each tier's max_horizontal_nm/max_vertical_ft) comes from cfg, never hardcoded in the code. A change to the YAML changes behavior without a code change, and config_version lets a past detection be explained by the exact rules that produced it.
Both functions use strict <, not <=, on every threshold. An aircraft sitting exactly on a tier boundary falls into the next, looser tier rather than the tighter one — verified directly by the tests (e.g. exactly 0.5 nm does not count as HIGH).
flag_pair's gates are ordered cheapest/most-disqualifying first (existence and direction checks before the tier lookup), so a pair that's diverging or has no velocity never reaches severity_for at all.

## What it does NOT handle
*Known limits. These feed the detector's `limitations` list and the Week-13
explainability deliverable, so be honest here.*

No hysteresis or debouncing — a pair sitting right on a tier boundary can flap between severities from one tick to the next; smoothing that out (if needed) is up to whatever calls flag_pair repeatedly, not these functions.
flag_pair only trusts a straight-line, constant-velocity prediction out to cfg.max_tcpa_s (120s by default). Anything beyond that horizon is simply not evaluated — it abstains rather than guessing at a maneuver.
No awareness of context that might make a close pair legitimate — formation flying, ATC-cleared separation, aircraft type, etc. A converging pair that crosses a tier is flagged the same way regardless of why it's close.
No trend or history — each call judges one instant's prediction in isolation; whether the pair was closing faster or slower a moment ago isn't reconsidered here (that logic lives upstream, in the geometry that computes t_cpa_s and converging).

## Tests
`tests/air/detectors/proximity/test_<file>.py` — <n> tests.
*One line on what the positive case and the negative/benign case are.*
all say xpassed for tests