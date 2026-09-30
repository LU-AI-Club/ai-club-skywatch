# interpolate_to_grid

**Author:** Erik Ellis · **PR:** #11 · **File:** `air/detectors/proximity/tracks.py`

## What it does
Aircraft report their position at random moments, so two planes' reports almost
never line up in time. This function takes one aircraft's reports and fills in
where it was at every whole second between its first and last report. Every
plane ends up on the same clock, so the later steps compare positions at the
exact same instant instead of inventing near-misses from mismatched timestamps.

## Inputs and outputs
| | Type | Units | Notes |
|---|---|---|---|
| in | `list[AdsbObservation]` | — | One aircraft only, sorted by time (from `group_tracks`) |
| in | `step_s: float` | seconds | Grid spacing, from config `grid_step_s` (1.0). Must be a whole number of microseconds |
| in | `max_gap_s: float` | seconds | Longest silence we'll blend across, from config `max_gap_s` (30.0). Inclusive |
| out | `list[AdsbObservation]` | — | One observation per grid tick, in time order, no duplicates. Empty if fewer than 2 reports |

## How it works

> Drafted from the merged code so the PR is complete — Erik, reword these in
> your own voice and correct anything I misread.

- **Work in whole microseconds, not floats.** Every timestamp is converted to
  an integer count of microseconds since the epoch, and `step_s` is rejected
  unless it is a whole number of microseconds. `datetime` cannot represent
  anything finer, so a step like 1.5 µs has no honest grid — better to refuse
  it than silently resample onto a different one.
- **Walk the reports in overlapping `(before, after)` pairs.** Each pair covers
  one segment of the track. A tick belongs to a segment if it falls between
  those two timestamps, so the whole track is covered by stepping through the
  pairs once.
- **Pick the ticks arithmetically, don't loop.** For a blendable segment the
  ticks are `ceil(before/step) .. floor(after/step)`. Computing the range
  directly means a ten-year gap at a microsecond grid costs the same as a
  two-second gap — a tick-by-tick loop would never finish.
- **Blend with `frac = (tick - before) / (after - before)`.** Position,
  altitude, speed and vertical rate are straight linear blends. The compass
  track uses `_lerp_angle`, which takes the short way round so 350° to 10°
  passes through 0 and not through 180.
- **A tick landing exactly on a real report returns that report untouched** —
  no arithmetic, so the original values and metadata survive rather than being
  recomputed from its neighbours.
- **Don't invent positions across a silence.** If a segment spans more than
  `max_gap_s`, only ticks sitting exactly on the two real reports are emitted;
  everything between them is skipped. The gap is compared in seconds, because
  scaling `max_gap_s` into microseconds can push an exact boundary a hair below
  the integer span.
- **Duplicates are impossible by construction.** `last_k` records the index of
  the last tick emitted, and any tick at or below it is skipped — so the report
  shared by two adjacent segments is only emitted once.

## Decisions and trade-offs
- **Exact hits return the real report.** If a tick lands exactly on a report, I
  return that report unchanged instead of blending. Otherwise its callsign and
  squawk would be copied from the previous report, and a missing altitude on
  the neighbouring report would erase a real one.
- **Long gaps keep real reports but invent nothing.** Across a silence longer
  than `max_gap_s` no positions are blended, but a real report that sits on a
  tick is still kept. Dropping it would throw away real data.
- **Integer microseconds, not float seconds.** Timestamps are ~1.8 billion
  seconds since 1970. At that size float maths drifts off `:00.000`, which would
  put two planes on slightly different ticks.
- **Invalid settings raise errors.** A step that isn't a whole number of
  microseconds, or a NaN/negative gap, raises `ValueError` instead of silently
  using a different grid.
- **Duplicate timestamps:** the first report at that instant wins.

## What it does NOT handle
- **Straight-line only.** Blending assumes the plane flew straight at a steady
  rate between reports. A turn or climb change inside the gap is flattened.
- **Off-grid lone reports disappear.** A report surrounded by long gaps that
  doesn't land exactly on a tick produces nothing.
- **Trusts its input.** It assumes one aircraft, sorted by time. Unsorted input
  gives wrong output with no error.
- **No quality filtering.** Bad positions (low NIC/NACp, spoofing) are blended
  like good ones. That's another stage's job.
- **Missing values stay missing.** If either neighbouring report lacks altitude
  or heading, the blended ticks get `None`. We don't guess.

## Tests
`tests/air/detectors/proximity/test_proximity_tracks.py` — 45 tests.
Positive: two reports 10 s apart give a correct blended position at every whole
second in between. Negative: reports 98 s apart give no invented positions
across the gap, only the real reports.
