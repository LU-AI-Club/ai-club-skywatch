# No-Fly-Zone Team — Live Integration Guide

Your team's work to get `skywatch.no_fly_zone` running continuously on the live
ADS-B stream. You own **two things this week**:

1. **Spine component C — the live runner harness** (shared infrastructure the
   *other two teams run on*).
2. **Your detector's live lane** — detection table, mapper, and validation.

Shared context: [`SPINE_PLAN.md`](SPINE_PLAN.md) (the full contract) and
[`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md) (the table base).
Everything finishes to the repo's definition of done: **a merged PR with a
`pytest` test on a fixture — no live services in the test**
(`docs/DETECTOR_PLAYBOOK.md`).

> **Why your team owns C:** the runner must handle **stateful** detectors that
> keep findings open across windows — and no-fly-zone is exactly that (incursion
> episodes span entry→exit via `flush()`). You already understand that behavior,
> so you're best placed to make the harness honor it for everyone.

**Dependencies:** C depends on **A** (Spoofing's reader) and **B** (Proximity's
persistence). Build against their **frozen interfaces / stubs** from day 1 — start
on the loop skeleton, cursor logic, and `flush()` handling, which need neither
implementation — and integrate once A and B land. The Tech Lead freezes the
interfaces (day 1) and provides the base runner **image**, the Compose services,
and the generic `run_live_detector.py` entry that calls your `run_live` — so
there is **no per-detector runner service for any team to build** (see
[`../../docker/README.md`](../../docker/README.md)) — plus the observations API
and the local populate script.

---

## Part 1 — Spine C: live runner harness  *(shared; everyone runs on it)*

**Module:** `air/live/runner.py`

**Goal.** Run one detector continuously: read a rolling window via **A**, detect,
dedup, persist via **B**, on a timer. One harness, parameterized per detector —
the other teams do not write their own loop.

**Interface (freeze this on day 1):**

```python
def run_live(
    *,
    detector,                 # object with detect_observations() (+ optional flush())
    table: str,
    dsn: str,
    window_s: float,          # rolling lookback W (per-detector)
    step_s: float,            # how far the cursor advances each tick
    poll_interval_s: float,   # sleep between ticks
    extra_columns=None,       # passed through to persistence.persist
    domain: str = "air",
    once: bool = False,       # single pass, for tests/CI
) -> None:
    ...
```

**Behaviors to build:**
- **Cursor / watermark.** Track the latest `observed_at` processed; each tick read
  `[cursor - window_s, now]` via `observations_reader.read_window` so work is
  proportional to new data plus a bounded lookback tail — never the whole history.
  The cursor survives restarts (persist it via `detector_runs` or a small record).
- **Rolling window + dedup.** Consecutive windows overlap by `window_s - step_s`;
  `persistence.persist` collapses the overlap on `dedup_key` — you don't dedup
  yourself, you just pass detections through.
- **Stateful detectors (the reason this is your team's):** when the detector
  exposes `flush()`, call it appropriately so an incursion spanning a window edge
  is **one** episode, not two. Getting this right once, here, is the whole point.
- **Resilience.** Survive a DB hiccup or a bad window without dying; one
  structured log line per tick (counts, lag); clean shutdown on SIGTERM.
- **`once=True`** runs a single tick — this is what every team's end-to-end test
  calls.
- Wrap each run in `persistence.start_run` / `finish_run` for the heartbeat.

**Done when:** `run_live(..., once=True)` takes a seeded `observations` table
through read → detect → persist in one pass (the reference end-to-end other teams
copy), with a fixture test; and a continuous run against the local DB shows the
cursor advancing and no duplicate rows across a restart.

**Coordinate with the Tech Lead:** they build the base container image and the
Compose service entries; your harness is what those services invoke. Agree on the
env/params contract (detector name, `table`, `window_s`, `step_s`,
`poll_interval_s`, `SKYWATCH_DB_DSN`).

**Suggested tickets:**
- `C1` Define & document the `run_live` signature; stub + interface test; agree the env/param contract with the Lead.
- `C2` Loop skeleton + `poll_interval_s` timer + `once=True` single-pass path.
- `C3` Cursor/watermark: compute the window, advance, persist/restore across restarts.
- `C4` Wire in A (`read_window`) and B (`persist`, run heartbeat) — against stubs until they land.
- `C5` `flush()` handling for stateful detectors (episodes across windows).
- `C6` Resilience: error isolation per tick, structured logging, SIGTERM shutdown.
- `C7` Reference end-to-end test with `once=True` over a seeded fixture.

---

## Part 2 — No-fly-zone detection table

**Goal.** Create `db/schema/004_no_fly_zone_detections.sql` (table
`no_fly_zone_detections`) from the base template in `DETECTION_TABLE_COLUMNS.md`.

- Keep the shared columns; add NFZ's extra columns: `zone_id`, `zone_name`,
  `zone_type`, `duration_seconds`. Add a `(zone_id, temporal_bounds_start DESC)`
  index.
- **Done when:** the migration applies to the local DB and matches your mapper.

**Suggested tickets:** `T1` draft from template + extra columns; `T2` confirm
name/columns with the Lead; `T3` verify load via `docker compose up -d db`.

## Part 3 — `Detection` → row mapper

**Goal.** `extra_columns(detection) -> dict` returning `zone_id`, `zone_name`,
`zone_type`, `duration_seconds` (from the detection's `geospatial_context` /
`metadata`). Shared columns are filled by `persist`.

- **Done when:** a unit test maps a sample incursion `Detection` to the expected
  row and `persist` writes it.

**Suggested tickets:** `M1` implement `extra_columns`; `M2` fixture test.

## Part 4 — End-to-end + live validation

**Goal.** Prove the chain, especially episode continuity across windows, and that
thresholds hold on live data.

- End-to-end: `run_live(..., once=True)` (and a two-tick case) over a seeded
  `observations` fixture with an incursion crossing a window edge → assert **one**
  episode row.
- Live smoke: check alert rate / false positives against the real stream, capture
  a real-world fixture or two. Re-tune only if live disagrees with fixtures.
- **Done when:** the e2e tests are green in CI + a short note on live behavior.

**Suggested tickets:** `E1` e2e `once=True` test; `E2` cross-window episode test;
`E3` live smoke + fixture capture; `E4` behavior note / threshold confirmation.

---

## Conventions (do not violate)

- **Detectors stay pure.** DB I/O lives in the spine; `air/detectors/no_fly_zone/`
  still only takes `list[AdsbObservation]` → `list[Detection]` (plus its existing
  `flush()`).
- **Import `Detection` from `contracts/`; never redefine it.**
- **Confidence is about a deviation, not threat** — TCE owns Trust downstream.
- **Abstain over guess**, and **every task ends with a fixture test.**
- C is shared infra that A and B plug into: coordinate the signature; the other
  teams' runners depend on it.
