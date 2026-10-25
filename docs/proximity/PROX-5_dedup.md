# PROX-5 — One encounter, counted several times

**Author:** Erik Ellis · **Type:** Spike · **Branch:** `proximity/erik/prox-5-dedup`

## Summary
The proximity detector reports **one detection per aircraft pair per call**.
The replay runner calls it **once per time window**, and nothing links one
window to the next. So an encounter that lasts longer than a window is reported
again in every window it touches. On the Lynchburg hour, **over half of all
proximity detections are repeats of a pair already reported**, and the total
count depends on how the runner slices time rather than on what is in the sky.

## Evidence (Lynchburg hour, `data/lynchburg_adsb.csv`)
Same data, same detector, same config — only the runner's window changes:

| Runner setting | Detections | Unique pairs |
|---|---|---|
| one 3,600 s window (whole hour) | **543** | 543 |
| 60 s tumbling (default) | 1,128 | 534 |
| 30 s tumbling | 1,509 | 523 |
| 60 s sliding, 20 s step, dedup on | **2,037** | 543 |

```bash
python scripts/replay_csv.py --detector proximity --window 3600 --out p3600.jsonl
python scripts/replay_csv.py --detector proximity --out p60.jsonl            # default 60 s
python scripts/replay_csv.py --detector proximity --window 30 --out p30.jsonl
python scripts/replay_csv.py --detector proximity --window 60 --step 20 --out p60_20.jsonl
```

- At the default 60 s window, 1,128 detections cover only 534 pairs: **594 rows
  (53%) are repeats.** One pair (`ae6230`/`ae624a`) is reported 16 times.
- The repeats are the *same* encounter, not new ones. Splitting each pair's
  detections into episodes wherever there's a gap of more than 120 s gives
  **599 episodes**; more than 300 s gives 549 — close to the whole-hour 543. Most
  repeats are 0–90 s after the previous one, i.e. the next window.
- **The existing dedup does not help.** `run_detectors(dedup=True)` is meant for
  sliding windows, but sliding windows *triple* the output (2,037).

## Root cause
1. `ProximityDetector.detect_observations` keeps the best instant per pair, but
   only within one call. Each window is a fresh call.
2. `air/windowing.detection_dedup_key` includes `temporal_bounds.start_time`,
   which for proximity is the tick the pair was evaluated at. Every window
   evaluates at a different tick, so the key never matches across windows and
   nothing is collapsed (pinned by `test_dedup_key_differs_between_windows`).
3. Nothing about the detector's maths is wrong. Each half of the encounter, seen
   alone, really is a converging pair inside `max_tcpa_s`
   (`test_each_window_alone_flags_the_pair`).

## A second finding: small windows also *lose* encounters
Unique pairs drop from 543 (whole hour) to 534 (60 s) to 523 (30 s). A window
edge cuts each track in two. `interpolate_to_grid` can't blend across the cut,
and a pair whose reports are split thinly across an edge may never be co-present
on a tick in either half. So windowing both **double-counts** long encounters
and **misses** a few short ones (~2–4%). Any fix should handle both.

## Options
| | Approach | Pros | Cons |
|---|---|---|---|
| A | **Detector keeps encounter state across calls**, emits an encounter when the pair has been quiet for a gap, `flush()` at end of stream | Same pattern NFZ already shipped (PR #57: `EpisodeTracker` + runner `flush()` hook); one detection per encounter regardless of windowing; also fixes the lost-encounter problem if it keeps a short tail of each track | Detector is no longer stateless per call; one-shot callers must call `flush()`; needs the `flush()` hook, which is on `main` but not on `Proximity_Detector` yet |
| B | **Change the runner's dedup key** to pair + "episode" (e.g. bucket `start_time`) | Small, runner-only | Bucketing still splits at bucket edges; key logic becomes proximity-specific inside shared infra |
| C | **Overlapping context window + idempotent upsert keyed on a stable encounter id** (what `windowing.py` says production does) | The real production answer | Needs a store; out of scope for the no-database replay |

## Recommendation
**Option A, matching NFZ.** The runner already has the hook on `main`, the NFZ
team proved the pattern (byte-identical CLI vs runner on the same hour), and it
keeps the dedup logic in the detector that understands what an "encounter" is.

Proposed rule (config-driven, nothing hard-coded):
- An encounter is a run of flagged ticks for the same pair. It stays open until
  the pair has gone `encounter_gap_s` without being flagged. Suggest
  `encounter_gap_s = max_tcpa_s` (120 s): the 120 s split already brings 1,128
  down to ~599, and an encounter can't sensibly outlive the prediction horizon.
- Emit once per encounter, keeping the instant with the smallest predicted
  horizontal separation (the same rule `detect_observations` uses today).
- `flush()` emits encounters still open at end of stream.
- Keep the last `max_gap_s` of each aircraft's reports between calls so tracks
  can be interpolated across the window edge (fixes the lost-encounter finding).

Expected effect on the Lynchburg hour at 60 s windows: **~1,128 → ~550–600**,
before PROX-1/PROX-2 (Emmanuel, #64/#65) remove far-apart and vertically
separated pairs.

**Needs the Tech Lead's call** before implementing: it changes the detector's
call contract (stateful + `flush()`), and depends on bringing the runner hook
from `main` into `Proximity_Detector`.

## What this spike delivers
- `air/fixtures/proximity_spans_window.json` — one head-on encounter whose
  reports straddle the 00:31:00 window edge (generated by
  `scripts/make_proximity_fixtures.py`, deterministic).
- `tests/air/detectors/proximity/test_proximity_windowing.py`:
  - passing: the fixture straddles an edge; one-shot and whole-hour runs give 1
    detection; each half alone flags the pair; the dedup key differs per window.
  - **strict xfail** (the bug, pinned): 60 s and 30 s tumbling windows and
    60/20 sliding windows should give 1 detection, currently give 2. When the
    fix lands these XPASS and strict mode forces the marker to be removed.
- The fixture is also in `test_proximity_detector.py`'s one-shot table
  (expects 1, HIGH).

## Deliberately left alone
- No change to the detector, runner, or dedup key — the fix changes a shared
  contract and needs Tech Lead sign-off first.
- Whether two genuinely separate encounters of the same pair inside the hour
  should be two events (Option A says yes; the whole-hour run says no). The
  episode gap decides this.
