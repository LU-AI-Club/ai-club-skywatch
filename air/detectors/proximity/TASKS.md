# Proximity detector — task board

## What we're building

Aircraft constantly broadcast where they are, how fast they're going, and which
way they're pointed. We take a recording of those broadcasts and ask, for every
pair of aircraft near each other: **if they both keep flying straight, how close
will they get, and when?** If the answer is "closer than the safe separation
distance, within the next two minutes," we flag it.

The important word is **predict**. We are not measuring how far apart two planes
are right now — anyone can do that. We are projecting them forward in time.

## How the work is split

The detector is a chain of steps. Each step is one small function: data goes in,
data comes out, nothing else happens. Because we already wrote down what each
function receives and what it has to return, you can build yours without waiting
on anybody. They will fit together at the end because the shapes were agreed
first.

```
all the recorded reports
   │  step 1: put every plane on the same clock        ← Erik
   ▼
a snapshot of the sky, once per second
   │  step 2: pick out the pairs worth checking        ← CalebG
   ▼
pairs that are close, flying, and not stacked
   │  step 3: do the closest-approach math             ← Manni
   ▼
how close they'll get, and in how many seconds
   │  step 4: decide how serious that is               ← CalebK
   ▼
HIGH / MEDIUM / LOW / INFO / nothing
   │  step 5: build the alert                          (already written)
   ▼
one alert, ready to hand to Xenith                     ← Paul wires it all together
```

Your job is to open one file, find the line that says
`raise NotImplementedError`, and replace it with real code. The comment above
that line explains exactly what to compute, including the formula. The tests are
already written, and they tell you the exact inputs and the exact answers
expected.

## Step 0 — install the test tools (first time only)

Your virtual environment must be active — your terminal prompt starts with
`(.venv)`. From the repo root:

```bash
pip install -e ".[dev,eda]"
```

That installs pytest (the test runner) plus pandas and matplotlib.

If you see `pytest : The term 'pytest' is not recognized`, you skipped this
step. If it still doesn't work after installing, use `python -m pytest`
instead of `pytest` everywhere below — same thing, just a longer name.

## See the board

```bash
pytest tests/air/detectors/proximity -q -rxX
```

This prints one letter per test, and a list underneath saying who owns each
one. It is how we all see what is finished.

| Letter | Means |
|---|---|
| `x` | nobody has written this yet |
| `X` | someone wrote it and it works |
| `F` | someone wrote it but the answer is wrong |
| `.` | finished and signed off (the `@todo` line was removed) |

Right now almost everything is `x`. Find your name in the list — those are
your tests.

To run only your own tests, use your own test file. The exact command is
written at the top of every test file.

## The loop — what you do, start to finish

```bash
# 1. Go to the team branch and get everyone else's latest work.
git checkout Proximity_Detector
git pull

# 2. Make your own branch. Name it after yourself and your function.
git checkout -b proximity/<yourname>/<function>     # e.g. proximity/erik/interpolate

# 3. Open your file (your card below says which one). Find the line
#    "raise NotImplementedError" and replace it with real code.
#    READ THE COMMENT ABOVE IT FIRST — the formula is in there.

# 4. Run your tests. Go back to step 3 and try again until they pass.
#    Adding -x makes it stop at the first failure so you fix one thing at a time.
pytest tests/air/detectors/proximity/test_proximity_<file>.py -x -q

# 5. Open your test file and delete every line that says @todo("YourName").
#    Only delete the ones above tests that now pass. This is how the board
#    shows your work is finished.

# 6. Write up what you built (see "Step 6 explained" below).
cp docs/proximity/_TEMPLATE.md docs/proximity/<function>.md

# 7. Run the whole test suite to check you didn't break anyone else's work.
pytest -q

# 8. Save your work and send it to GitHub.
git add -A
git commit -m "proximity: implement <function>"
git push -u origin proximity/<yourname>/<function>

# 9. Go to github.com. There will be a green "Compare & pull request" button.
#    Click it, then CHANGE THE BASE DROPDOWN FROM main TO Proximity_Detector.
#    Write the description (format is in docs/proximity/PR_GUIDE.md), submit,
#    and ask a teammate to review it.
```

### Step 6 explained

Every piece of work gets a short write-up so the rest of us can understand it
without reading your code. It lives in `docs/proximity/` and goes in the same
pull request as the code.

**Make your copy.** From the repo root:

```bash
cp docs/proximity/_TEMPLATE.md docs/proximity/<function>.md
```

Replace `<function>` with your function's name, so Erik runs:

```bash
cp docs/proximity/_TEMPLATE.md docs/proximity/interpolate_to_grid.md
```

`cp` works in PowerShell too. If for any reason it doesn't, open
`docs/proximity/_TEMPLATE.md` in VS Code, use **File → Save As**, and save it
into the same folder under your function's name.

**Then open your new file and fill in every section.** It has six:

| Section | What to write |
|---|---|
| What it does | Two or three sentences in plain English. What goes in, what comes out, why the detector needs it. |
| Inputs and outputs | Fill in the little table: type, units, anything surprising. |
| How it works | 3–5 bullets on your approach. Include the formula. Not a line-by-line reading of your code — the reasoning behind it. |
| Decisions and trade-offs | Anything you chose that someone might question, and why you chose it. |
| What it does NOT handle | Honest limits. These become the detector's official caveats later, so don't skip this. |
| Tests | Name your test file and say in one line what the passing case and the failing case are. |

**Write it in your own words.** This is the part that proves you understand
what you built, not just that you got the tests green. Half a page is plenty.

## The rules

- **Pure functions only.** Same input always gives the same output. No reading
  files, no internet, no printing, no changing things outside your function.
- **When you can't tell, don't guess.** If a piece of data is missing, return
  `None` / `False` / an empty list. Never invent an answer.
- **Never type a threshold number into your code.** Every number comes from
  `configs/detectors/proximity.yaml`. If you find yourself typing `120` or
  `0.5`, stop and read the config instead.
- **Branch off `Proximity_Detector`, submit to `Proximity_Detector`.** Nothing
  goes to `main` for a long time.

## Using AI on your task

You're expected to use it. But the point of this is that you understand what
you built, so:

1. Read the comment above your function, and read your tests, **before** asking
   AI anything.
2. Work one test case out on paper first. Then use AI for syntax and debugging.
3. The "How it works" section of your write-up has to be in your own words.
   That's the checkpoint. If you can't explain why your function works without
   looking at the screen, you're not done yet.

## Cards

### Erik — `air/detectors/proximity/tracks.py`, function `interpolate_to_grid`

**In one sentence:** planes report their position at random moments, so fill in
where each plane was at every whole second in between.

This is the hardest card and the most important. If two planes' positions are
compared at slightly different moments, we invent near-misses that never
happened — that's the number one cause of false alarms in this kind of
detector.

Blend the positions, altitude and speed evenly between the two nearest real
reports. The compass heading needs the short way round (350° to 10° passes
through 0, not through 180) — there's a helper called `_lerp_angle` already
written for that, and `_lerp` for the ordinary ones. If a plane went quiet for
more than 30 seconds, don't invent positions across that gap.

**Tests:** `tests/air/detectors/proximity/test_proximity_tracks.py` — 9 tests.

### Manni — `air/detectors/proximity/geometry.py`, four functions

**In one sentence:** given two planes' positions and speeds, work out how many
seconds until they're closest and how far apart they'll be at that moment.

This is the actual math of the detector. Four short functions, each with its
formula written in the comment above it:

- `to_local_xy` — turn latitude/longitude into plain metres east and north.
  Don't forget the `cos` term; without it every east-west distance is 20% too
  big.
- `velocity_xy` — split speed and heading into an east component and a north
  component. It's `sin` for east and `cos` for north, which is the opposite of
  what you learned in math class, because compass angles start at north and go
  clockwise.
- `time_to_cpa` — `t_cpa = -(r·v)/|v|²`. Positive means they're still closing.
  Negative means they already passed each other.
- `predicted_separation` — slide both planes forward to that moment and measure
  the gap.

`haversine_nm` at the top of the file is already written — read it first as an
example of the style.

**Tests:** `tests/air/detectors/proximity/test_proximity_geometry.py` — 17 tests.

### CalebG — `air/detectors/proximity/pairs.py`, two functions

**In one sentence:** out of everyone in the sky at one instant, list the pairs
worth checking, and throw out the obvious non-problems.

Not much math, but the logic has to be exactly right.

- `is_airborne` — is this plane actually flying? Two lines, both numbers from
  the config. A plane that's low **and** slow is on the ground. Low and fast is
  landing. High and slow is a helicopter hovering. Both of those are flying.
- `candidate_pairs` — comparing every plane to every other plane is 400,000
  comparisons a second, which is far too slow. So drop planes into map squares
  (`cell_of` is already written for you) and only compare planes in the same
  square or a touching one. Then throw out pairs where one is on the ground, or
  where they're more than 2000 ft apart vertically.

Start with `is_airborne`. It's five tests and about twenty minutes.

**Tests:** `tests/air/detectors/proximity/test_proximity_pairs.py` — 14 tests.

### CalebK — `air/detectors/proximity/detector.py`, two functions

**In one sentence:** given how close two planes are predicted to get, decide
whether that's HIGH, MEDIUM, LOW, INFO, or nothing at all.

You're writing the rulebook. **Every number comes from the config file** — if
you type a number into your code, you've done it wrong.

- `severity_for` — walk down the list of tiers in the config and return the
  first one where **both** the sideways distance and the up-down distance are
  under the limit. Both. Two planes 0.2 miles apart sideways but 2000 ft apart
  in altitude are completely normal and get nothing.
- `flag_pair` — before looking anything up, check the basics: are they actually
  getting closer (not already past each other), and is it happening within the
  next 120 seconds? If either fails, return nothing.

Watch the boundaries: the tier says "under 0.5", so exactly 0.5 does **not**
count as HIGH — it falls to the next tier down.

**Tests:** `tests/air/detectors/proximity/test_proximity_rules.py` — 19 tests,
but 12 of those are the same table checked at 12 different values, so it's
smaller than it looks.

### Paul — `air/detectors/proximity/detector.py`, `detect_observations`

**In one sentence:** run all four stages in order and produce one alert per
pair of aircraft.

One alert per *pair*, not per second — a 90-second encounter is one event, not
90 alerts. Keep the moment where they were predicted to get closest. The
pseudo-code is in the comment above the function.

This one can only go green once everybody else's is finished. When it does:

```bash
python scripts/run_proximity.py air/fixtures/proximity_head_on.json
```

prints a real alert as JSON. **That's the Week 6 deliverable.**

**Tests:** `tests/air/detectors/proximity/test_proximity_detector.py` — 9 tests.

### Caroline & Faith — `air/detectors/proximity/DESIGN_CARD.md`

**In one sentence:** write the one-page document that explains to Xenith what
this detector does and what it can't do.

No code. The file has eight boxes with a hint under each one saying where the
answer lives — mostly in `docs/proximity/PROJECT_PLAN.md`. Read, find the
answer, write it in your own words in two or three sentences. Don't paste the
plan in; a design card that's a copy of the plan isn't a design card.

This is a graded deliverable the club has to produce, not a warm-up exercise.
Check it with Paul, then submit it the same way everyone else does — your own
branch, then a pull request — just a `.md` file instead of a `.py`.

## When you're stuck

1. **Read the comment above your function again, slowly.** The formula is
   there.
2. **Read the failing test.** It tells you the exact input and the exact
   expected output. Work that one case out by hand on paper — usually the
   mistake becomes obvious.
3. **Ask Paul.** Not finishing inside the hour is completely normal. Ask before
   you sink your weekend into it.

## Already done — don't rebuild these

| What | Where |
|---|---|
| All the threshold numbers, loaded from config | `config.py`, `configs/detectors/proximity.yaml` |
| Distance between two lat/lon points | `geometry.haversine_nm` |
| Grouping reports by aircraft, assembling per-second snapshots | `tracks.group_tracks`, `tracks.align_tracks` |
| Which map square a plane is in | `pairs.cell_of` |
| Gluing Manni's four functions into one record | `detector.pair_geometry` |
| Scoring and building the final alert | `detector.confidence_for`, `explanation_facts`, `to_detection` |
| Five test scenarios with known answers | `air/fixtures/proximity_*.json` |
| The script that regenerates them | `scripts/make_proximity_fixtures.py` |
| The command-line runner | `scripts/run_proximity.py` |
