# Task: build the detection review sheet

**Owners:** Caroline, Faith · **Due:** next meeting · **No code.**

## Why this matters

Next week the detector runs on a real hour of air traffic and flags some
number of aircraft pairs. Then somebody has to look at each one and decide:
*was that a real conflict, or something perfectly normal that only looked like
one?*

Nobody labels near-misses in real flight data, so there is no answer key. The
only way we find out whether our detector works is for a person to review what
it flagged and write down a judgement. **You are building the sheet that
judgement gets recorded on, and next week you are the ones doing the
reviewing.**

This is the Week 7 deliverable — "labeled evaluation set and success metrics."
It's a graded item, and it belongs to you.

## What to hand in

One file: `docs/proximity/REVIEW_SHEET.md`

It has three parts.

### Part 1 — the columns

Design the table a reviewer fills in, one row per flagged pair. Decide what
each column is and write a one-line description of it. Some you'll definitely
want:

- which two aircraft, and when
- what the detector said (severity, how close it predicted they'd get, how many
  seconds away)
- what the reviewer decided
- why

Add anything else you think a reviewer would need. You're designing this, not
filling in a form we already wrote.

### Part 2 — the verdict categories

This is the real work. A reviewer needs a short list of choices, not a free-text
box. Read the "False positives" section of
[PROJECT_PLAN.md](PROJECT_PLAN.md) and turn it into categories a person can
pick from. Something like:

- **Real** — genuinely close, nothing explains it away
- **Landing queue** — aircraft lined up for the same runway, normally 3 nm
  apart. Expected to be the most common one.
- **Parallel runways** — side by side on purpose
- ... and so on for the rest of the list
- **Can't tell** — a real option. Say so rather than guessing.

For each category, write one or two sentences on **how a reviewer would
recognise it**. That's the hard and useful part: "how would I know this is a
landing queue and not a real conflict?" Hints: are they both descending? Are
they pointed the same direction? Are they near an airport?

### Part 3 — how to use it

Half a page. If a new person sat down with this sheet and a list of flagged
pairs, what would they do, step by step? Write that.

## Where to find things

| You need | Look in |
|---|---|
| the list of benign situations | `docs/proximity/PROJECT_PLAN.md`, "False positives" |
| what the detector reports about each pair | `docs/proximity/PROJECT_PLAN.md`, "Output contract" |
| the severity thresholds | `configs/detectors/proximity.yaml` |
| a map of where the traffic is | `notebooks/example_eda.ipynb` — the scatter plot. The dark clusters are airports. |

## Two rules

- **Write what a reviewer observes, never a conclusion.** "Both descending,
  same heading, 8 nm from Charlotte" is an observation. "This was dangerous"
  is not ours to say — a separate Xenith system makes that call.
- **"Can't tell" is a valid verdict.** Honest uncertainty is worth more than a
  confident guess, and the project plan says so explicitly.

## Submitting

Same as everyone else on the team:

```bash
git checkout Proximity_Detector
git pull
git checkout -b proximity/caroline-faith/review-sheet
# create and write docs/proximity/REVIEW_SHEET.md
git add -A
git commit -m "proximity: add the detection review sheet"
git push -u origin proximity/caroline-faith/review-sheet
```

Then on github.com, click **Compare & pull request**, change the base dropdown
from `main` to `Proximity_Detector`, and submit. Ask Paul if any of that is
unclear — the git part is new for you and that's fine.
