# How the detector works, end to end

Read this once and you'll know where everything lives. About ten minutes.

## Try it first

```bash
git checkout Proximity_Detector
git pull
pytest -q
python scripts/run_proximity.py air/fixtures/proximity_head_on.json
```

One alert prints out. The rest of this explains where it came from.

## What we're doing

Planes broadcast where they are, how fast they're going and which way they're
pointed. We read a recording of those broadcasts and ask, for every pair of
planes near each other:

> **If they both keep flying straight, how close will they get, and when?**

If the answer is too close, too soon, we raise an alert.

The word that matters is **predict**. We don't measure how far apart two planes
are right now — that's easy and it's useless. We project them forward.

## The input

Open `air/fixtures/proximity_head_on.json`. Two aircraft, `aaa001` and
`bbb002`, flying straight at each other.

Look at the timestamps:

```
aaa001 reports at  :00.0   :02.3   :04.9   :07.6
bbb002 reports at     :01.1   :03.4   :06.2   :08.7
```

**They never report at the same moment.** That's what real data looks like, and
it's why the first step of the pipeline exists.

## The six steps

The detector is six small pieces in a row. Data goes in one end, an alert comes
out the other. Each piece is one file.

```
recorded flight data
   │
   │  1. read the file                      air/normalizers/wingbits_csv.py
   ▼
list of aircraft reports
   │
   │  2. put everyone on the same clock     air/detectors/proximity/tracks.py
   ▼
a snapshot of the sky, once per second
   │
   │  3. pick pairs worth checking          air/detectors/proximity/pairs.py
   ▼
nearby pairs
   │
   │  4. do the closest-approach math       air/detectors/proximity/geometry.py
   ▼
how close they'll get, and when
   │
   │  5. decide how serious that is         air/detectors/proximity/rules.py
   ▼
HIGH / MEDIUM / LOW / nothing
   │
   │  6. build the alert                    air/detectors/proximity/detector.py
   ▼
one alert, ready to send to Xenith
```

### 1. Read the file — `air/normalizers/wingbits_csv.py`

The raw file is a 70 MB CSV with 53 columns and cryptic names: `h` for the
aircraft ID, `la` and `lo` for position, `ab` for altitude. This file reads it,
keeps the 11 columns we need, throws out broken rows, and turns each one into a
standard Python object.

**This is the only file in the whole project that knows a CSV exists.** If we
switch to a live antenna later, we write a new version of this file and nothing
else changes.

### 2. Same clock — `air/detectors/proximity/tracks.py`

The problem from above. If you compare plane A at 12:00:03 against plane B at
12:00:07, you're comparing two different moments — and four seconds at jet speed
is half a mile. You'd invent collisions that never happened.

So this file fills in where every plane was at every whole second. Now when we
compare two planes, we're comparing the same instant.

One tricky bit: compass headings. Going from 350° to 10° is a small turn through
north, but doing the math the obvious way swings the plane all the way around
through south. There's a special function (`_lerp_angle`) just for that.

### 3. Pick pairs — `air/detectors/proximity/pairs.py`

With 900 planes, checking every plane against every other is 400,000
comparisons per second of data. Almost all of those pairs are hundreds of miles
apart.

So this file drops planes into squares on a map and only compares planes in the
same square or next door. It also throws out anything on the ground and any pair
more than 2,000 ft apart vertically.

### 4. The math — `air/detectors/proximity/geometry.py`

This is the actual detector. Four short functions:

- `to_local_xy` — turn latitude/longitude into plain metres
- `velocity_xy` — split speed and heading into east/north components
- `time_to_cpa` — **the core formula.** Given where two planes are relative to
  each other and how fast they're closing, solve for when they'll be nearest:
  `t = -(r·v) / |v|²`. A negative answer means they already passed.
- `predicted_separation` — slide both planes forward to that moment and measure
  the gap

### 5. Decide — `air/detectors/proximity/rules.py`

Six gates. **Fail any one and we stay quiet:**

1. Is there relative motion between them?
2. Are they actually getting closer, not already past each other?
3. Does it happen within the next 120 seconds?
4. Do we have predicted distances?
5. Are they already within 10 nautical miles?
6. Are **both** above 5,000 feet?

Survive all six, and we look the predicted gap up in a table:

| Severity | Horizontal | Vertical |
|---|---|---|
| HIGH | under 0.5 nm | under 400 ft |
| MEDIUM | under 1.5 nm | under 700 ft |
| LOW | under 3 nm | under 900 ft |

**Both** limits have to hold. Two planes a quarter-mile apart but 2,000 ft above
each other are completely fine.

**Gates 5 and 6 are new this week.** They are what took us from 1,128 alerts to 3.

### 6. Build the alert — `air/detectors/proximity/detector.py`

Packages everything into the format Xenith's platform expects: the two aircraft,
a severity, a confidence score, plain-English explanation lines, known
limitations, and the exact config that produced it.

One alert per *pair*, not per second — a 90-second encounter is one event.

## Two more files worth knowing

**`configs/detectors/proximity.yaml`** — every threshold, with the reasoning in
comments. No number is typed into the code; they all live here. Read this one,
it's the most useful file in the project.

**`air/detectors/proximity/features.py`** — `PairGeometry`, the record that
carries the numbers from step 4 to step 5. It's the handoff between the math and
the rules.

## Where we stand

On a real hour of traffic — 915 aircraft within 200 miles of Lynchburg:

```
python scripts/replay_csv.py --detector proximity --quiet
```

**3 alerts.** A week ago it was 1,128. Four changes got us here, each with a
written explanation in `docs/proximity/PROX-*_root_cause.md`.

Then we tested the opposite question: *can we still catch a real collision?* We
scripted ten crashes and ran them through. See
`docs/proximity/RECALL_ANALYSIS.md`. Short version — we catch every collision
above 5,000 ft, and there are three things we can't do yet. Those three are
today's work.

## Reading order if you're lost

1. This file
2. `configs/detectors/proximity.yaml` — every number and why
3. `docs/proximity/RECALL_ANALYSIS.md` — what we can and can't detect
4. `docs/proximity/ARCHITECTURE.md` — the full technical version
