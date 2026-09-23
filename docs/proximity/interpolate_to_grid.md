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
TODO (Erik): 3-5 bullets in my own words — picking the ticks, walking the
reports in (before, after) pairs, the `frac` formula, the short-way heading,
and how duplicate ticks are avoided.

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
