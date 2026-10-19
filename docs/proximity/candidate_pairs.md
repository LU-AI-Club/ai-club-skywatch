# is_airborne / candidate_pairs

**Author:** CalebG · **PR:** #15 · **File:** `air/detectors/proximity/pairs.py`

> Drafted from the merged code so the folder is complete. CalebG: read it,
> correct anything that misstates what you did, and put the "How it works"
> bullets in your own words.

## What it does

Takes a snapshot of every aircraft in the sky at one instant and returns only
the pairs worth doing real math on. Comparing every aircraft against every
other is far too slow — 900 aircraft is roughly 400,000 comparisons per second
of data — and almost all of those pairs are hundreds of miles apart. This step
throws out the obvious non-problems cheaply so the expensive closest-approach
math only runs on plausible pairs.

## Inputs and outputs

| | Type | Units | Notes |
|---|---|---|---|
| in | `snapshot: list[AdsbObservation]` | — | Every aircraft at ONE grid tick, from `tracks.align_tracks` |
| in | `cfg: ProximityConfig` | — | Supplies `cell_size_deg`, `max_vertical_prefilter_ft`, `ground_altitude_ft`, `ground_speed_kt` |
| out | `list[tuple[AdsbObservation, AdsbObservation]]` | — | Each unordered pair once, sorted so `a.icao24 < b.icao24` |

`is_airborne` takes one observation plus the config and returns `True` / `False`.

## How it works

- **`is_airborne`** — an aircraft is on the ground only when it is *both* below
  the config altitude *and* slower than the config speed. Low and fast is an
  aircraft on final approach; high and slow is a helicopter hovering. Both are
  flying. If altitude or speed is missing, return `False` — we cannot judge, so
  we abstain.
- **Filter first** — drop anything that is not airborne, and anything missing a
  track or ground speed, since without a velocity there is nothing to project
  forward.
- **Bucket into grid cells** — `cell_of` turns each position into an integer
  `(row, col)` at `cell_size_deg` (0.5°, roughly 30 nm). Aircraft go into a
  dictionary keyed by cell.
- **Compare only neighbours** — for each cell, gather that cell plus its eight
  surrounding cells and pair its members against that group. Aircraft further
  apart than one cell are never considered at all, which is where the speed-up
  comes from.
- **Cheap rejects last** — skip a pair if the two IDs are the same, or if the
  altitude difference exceeds `max_vertical_prefilter_ft`. A set keeps each
  unordered pair once, and the result is sorted so the output is deterministic.

## Decisions and trade-offs

- **Nine cells, not a radius.** Checking a square block of cells is simpler and
  faster than computing a distance to decide what is "near". It over-collects a
  little at the corners, which costs nothing — the CPA math rejects those pairs
  anyway.
- **Missing data means `False`, never a guess.** An aircraft with no reported
  altitude is excluded rather than assumed airborne, following the project rule
  to abstain when evidence is insufficient.

## What it does NOT handle

- **Duplicate ICAO codes.** An aircraft transmitting under two IDs would be
  paired with itself and look like a perfect conflict. Only exact ID matches
  are caught.
- **Cell size is fixed at 0.5°.** Two aircraft closing head-on at jet speed can
  cover more than one cell within the 120-second prediction window, so a pair
  more than one cell apart right now could still matter. Widening the search as
  closure speed rises is future work.
- **The ground check uses a single altitude threshold above sea level.** Airport
  elevations vary (Lynchburg sits at 938 ft), so the speed check does most of
  the real work. Per-airport field elevations from FAA NASR are Week 9.
- **No context.** This step has no idea whether a pair is lined up for the same
  runway. That is deliberate — context filtering comes later.

## Tests

`tests/air/detectors/proximity/test_proximity_pairs.py` — 14 tests.
Positive case: two nearby airborne aircraft produce exactly one pair. Benign
cases: a pair stacked beyond the vertical limit, a pair taxiing on the ground,
and two aircraft three cells apart all produce nothing.
