# split_segments

**What it does:** breaks one aircraft's track wherever it went quiet for too long.
**File:** air/detectors/spoofing/features.py
**Inputs:** one aircraft's reports, and `max_gap_s` (default 60).
**Output:** a list of lists - the same reports, grouped into unbroken stretches.
**How it's tested:** a steady track stays one segment; a ten-minute silence splits it in two; a gap exactly at the limit does not split (the rule is 'longer than'); an empty track gives no segments.
**Gotchas:** this does not detect anything. Gaps are a condition to survive, not a finding to report.

## Why gaps have to break the track

Aircraft fall silent constantly and almost always innocently:

- out of receiver range, or below the horizon
- behind terrain
- powered down on a ramp
- shadowing their own belly antenna through a turn

Measuring speed across a ten-minute silence produces a number that means
nothing, because we have no idea what happened in between. Splitting first
removes that whole category of false positives in one step.

## The hole it leaves

If an aircraft goes dark and a *different* transmitter picks up its identity,
splitting the track means nobody notices. That is what `flag_reappearance`
exists for: at each boundary it asks whether the aircraft could have reached
where it came back. Segmenting and reappearance are two halves of one idea.
