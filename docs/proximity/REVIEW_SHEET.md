# Detection review sheet

**Owners:** Caroline, Faith · **Status:** DRAFT — fill in the blanks below.

When the detector flags two aircraft as coming close, a person has to look at it
and decide: was that a real conflict, or something completely normal that just
looked like one? This is the sheet they fill in.

---

## Part 1 — the table a reviewer fills in

One row per flagged pair. This part is done — you don't need to change it.

| Column | What goes in it |
|---|---|
| Pair | The two aircraft IDs |
| Time | When the detector flagged them |
| Severity | What the detector said: HIGH / MEDIUM / LOW / INFO |
| Predicted distance | How close it predicted they'd get, in nautical miles |
| Predicted altitude gap | How far apart vertically, in feet |
| Seconds away | How long until that closest moment |
| Verdict | One of the categories in Part 2 |
| Why | One sentence: what the reviewer saw that led to that verdict |

---

## Part 2 — the verdict categories

**This is your task.** For each category below, fill in the blank line with
**one or two sentences on how a reviewer would recognize it.** Think: what would
I look at on the map or in the numbers that tells me it's this one and not a
real conflict?

Everything you need is in
[PROJECT_PLAN.md](PROJECT_PLAN.md), section "False positives — the real work."

### Real conflict
Two aircraft genuinely close, and nothing on this list explains it away.

The aircraft are converging, and their predicted horizontal and vertical separation fall within the detector's thresholds. Their tracks do not match an identifiable pattern such as landing in sequence, approaching parallel runways, flying in formation, or taxiing on the ground.

### Landing queue
Aircraft lined up to land on the same runway. They're 3 miles apart on purpose.
This will be the most common one.

Both aircraft are near the same airport, descending, and traveling in roughly the same direction along the same runway heading. Their positions show one aircraft following the other toward the runway, with approximately 3 nautical miles between them.

### Parallel runways
Big airports have runways side by side. Aircraft land on them at the same time,
about 1 mile apart, completely normally.

Both aircraft are approaching an airport on nearly parallel tracks, with each aligned with a different parallel runway. Their lateral separation is approximately 1 nautical mile, and their paths show a parallel approach rather than a direct convergence.

### Stacked
Aircraft directly above one another, 1000 ft apart. That's the standard safe
spacing, not a problem.

The aircraft occupy nearly the same horizontal position but have approximately 1,000 feet of vertical separation. Their positions and altitude readings show that most of the separation is vertical rather than horizontal.

### Formation flight
Military or training aircraft flying deliberately close together.

The aircraft maintain very close spacing while traveling in the same direction, with similar headings, speeds, and altitudes over multiple observations. Their tracks remain together instead of showing the changing relative positions expected from two independently moving aircraft.

### Ground traffic
Aircraft taxiing at an airport, parked metres apart.

The aircraft are on or near an airport surface, moving at low speeds or remaining stationary, with very little distance between them. Check the reported on-ground status along with altitude and speed, since the on-ground field may not always be accurate.

### Can't tell
Not enough information to decide. **This is a real answer — use it.** Guessing
is worse than admitting you don't know.

The available positions, timestamps, altitude readings, or aircraft tracks are incomplete, inconsistent, or insufficient to match the pair to a recognizable pattern. For example, conflicting altitude information or an unclear approach path may prevent a reliable verdict.

---

## Part 3 — instructions for the reviewer

**Also your task.** Write 4 or 5 short steps telling a person what to do,
start to finish. Imagine someone who has never seen this sheet sits down with a
list of flagged pairs. What do they do first? Then what?

1. Review the flagged pair. Record the aircraft IDs, detection time, severity, predicted distance, predicted altitude gap, and seconds until closest approach.
2. Check the aircraft data. Examine their positions, headings, speeds, altitude readings, and recent tracks to determine whether they are converging and how their separation changes over time.
3. Look for normal flight patterns. Check whether the aircraft are near an airport or runway, descending in a landing queue, approaching parallel runways, vertically stacked, flying in formation, or moving on the ground.
4. Choose the best-fitting verdict. Select a category based on the available evidence. If none of the normal patterns explains the predicted proximity, choose Real conflict. If the evidence is insufficient or inconsistent, choose Can't tell.
5. Write a one-sentence explanation. Describe the specific evidence supporting the verdict, such as the aircraft's direction, altitude difference, predicted distance, or alignment with a runway. Record observable facts rather than claiming that an event was dangerous or that a violation occurred.

---

## Two rules to keep in mind while you write

- **Describe what the reviewer sees, not what it means.** "Both descending, same
  direction, 8 miles from Charlotte airport" is good. "This was dangerous" is
  not — a different Xenith system decides that, not us.
- **"Can't tell" is always allowed.** Honest uncertainty beats a confident
  guess.
