# No-Fly-Zone — Week 12 team handout

The live pipeline runs for no-fly-zone. This page is what is left, split so each
person can take one ticket and work without waiting on anyone else.

**How to take a ticket**

1. Put your name next to it in the [ticket list](#ticket-list) (edit this file in your PR).
2. Branch off `main`, PR into `main`. One ticket per PR.
3. Every ticket ends with a fixture test, no live services in tests
   (`docs/DETECTOR_PLAYBOOK.md`). Ticket IDs go in the PR title (`NFZ-12D: …`).
4. Read `air/detectors/no_fly_zone/AGENTS.md` first: `types.py` and
   `configs/detectors/no_fly_zone.yaml` are lead-owned, so ask Tim before changing them.

---

## Where things stand

| Piece | State |
|---|---|
| Detector, table, mapper (`live.py`) | ✅ Working; one row per incursion, opened on entry, closed on exit |
| Live runner (Spine C, ours) | ✅ Keeps up with live time, survives DB errors, stops cleanly, logs every tick (#122) |
| Zones | ✅ 15 real FAA zones committed: the Lynchburg area (within 65 nm of KLYH) plus P-56 over Washington DC (#120) |
| Live feed → `observations` | ✅ Poller works from an allowlisted machine |
| Live feed fields (altitude, squawk, NIC…) | ⏳ Reader fix in review: **#121** (Will). Until it merges, live data has **no altitude**, so NFZ skips every aircraft and still reports `SUCCESS` |
| `main` test suite | ⏳ One stale test fails (`test_live_spine`); fixed by **#116** (Will) |

**What the zones are.** Fort Pickett **R-6602A/B/C** (restricted) and **P-56**
(prohibited, always active) are the real "violation" zones. The 10 local MOAs
(Farmville, Evers, Barfoot) are military training airspace that civilian pilots
may legally fly through, so NFZ scores them LOW/INFO: context, not violations.

**Expect few detections.** Replaying one real hour of Lynchburg traffic over the
15 zones gave 2 detections (Evers South MOA, both LOW). The tickets below are
mostly about making the nearby zones *able* to fire and fire at the right
severity.

---

## Ticket list

| Track | Ticket | What | Size | Needs live data | Owner |
|---|---|---|---|---|---|
| **A · Detection quality** | [NFZ-12D](#nfz-12d--parse-the-local-zones-schedules) | Parse the local zones' schedules | M | No | |
| | [NFZ-12E](#nfz-12e--let-agl-floor-zones-fire) | Let AGL-floor zones fire (7 of 13 local zones can't) | M | No | |
| | [NFZ-12L](#nfz-12l--grade-confidence-instead-of-0-or-1) | Grade confidence instead of 0 or 1 | M | No | |
| | [NFZ-12M](#nfz-12m--apply-airspaceinclude_types) | Apply `airspace.include_types` | S | No | |
| **B · Live validation** | [NFZ-12N](#nfz-12n--end-to-end-tests-in-the-repo-e1e2) | End-to-end tests in the repo (E1/E2) | M | No | |
| | [NFZ-12O](#nfz-12o--live-smoke-test-and-behaviour-note-e3e4) | Live smoke test + behaviour note (E3/E4) | M | **Yes**, after #121 | |
| | [NFZ-12P](#nfz-12p--run-the-database-tests-in-ci) | Run the database tests in CI | S | No | |
| **C · Runner (Spine C)** | [NFZ-12K](#nfz-12k--skip-reasons-in-the-heartbeat) | Skip reasons in the heartbeat ("fail safely") | S | No | |
| | [NFZ-12Q](#nfz-12q--fail-fast-on-misconfiguration) | Fail fast on misconfiguration | S | No | |
| | [NFZ-12R](#nfz-12r--one-runner-per-detector) | One runner per detector (advisory lock) | S | No | |
| **D · Demo** | [NFZ-12H](#nfz-12h--live-incursions-on-the-dashboard) | Live incursions on the dashboard | M | No | |

Tracks don't depend on each other. Inside track A, 12D and 12E touch different
files (`logic/activation.py` vs `geo/altitude.py`) and can run in parallel.
12Q and 12R come from Nate's `docs/WEEK12_TODO.md` (tagged Spine C / Tech Lead),
so tell him when you pick one up.

---

## Track A · Detection quality

### NFZ-12D — Parse the local zones' schedules

**Files:** `scripts/make_faa_airspace.py`, `logic/activation.py`, `fixtures/airspace/klyh-local-faa.geojson`

**Why.** FAA "times of use" is free text, and only `CONTINUOUS` is understood
today. Every local zone except P-56 is therefore UNKNOWN activation, and UNKNOWN
caps severity at LOW (`severity.unknown_activation_cap`), so an aircraft in
Fort Pickett's restricted area during its published active season scores the same
as one in a cold MOA at midnight.

**The local zones use only four phrasings:**

| Zones | `times_of_use` |
|---|---|
| Farmville MOA ×3 | `0800 - 1700, MON - FRI; O/T BY NOTAM` |
| Evers South/Center/Low/East | `0630 - SUNSET, DAILY, BY NOTAM; OTHER TIMES BY NOTAM` |
| Barfoot 1–3 | `INTERMITTENT, SUNRISE - SUNSET, DAILY` |
| R-6602A | `MAY 1 - SEP 15, CONTINUOUS; OTHER TIMES BY NOTAM 24 HRS IN ADVANCE` |

(R-6602B/C are `BY NOTAM 24 HRS IN ADVANCE` only, and stay UNKNOWN.)

**Do.** Turn these into `active_windows` (local time is US Eastern). Decide and
document the meaning: inside a published window the zone is *scheduled* active;
outside it, "O/T BY NOTAM" means it *may* still be active, so stay UNKNOWN rather
than claiming it's cold. `INTERMITTENT` and sunrise/sunset need a choice too
(a small solar formula for KLYH is enough). Unparseable text stays UNKNOWN.

**Done when.** One test per phrasing (inside and outside the window), the
regenerated local file is committed, and the PR states how many of the 15 zones
now have known activation at a given time.

### NFZ-12E — Let AGL-floor zones fire

**Files:** `geo/altitude.py` (plus a small terrain grid)

**Why.** A floor like "300 FT SFC" means 300 ft *above the ground*, so it maps to
`Datum.AGL`, and the vertical check abstains on AGL because the detector has no
terrain model. **7 of the 13 Lynchburg-area zones have AGL floors** (Farmville
×3, Evers Low and East, Barfoot 1 and 2), so more than half the nearby airspace
can never alert. On the one-hour replay, 1,645 reports exited `bad_input`,
mostly here.

**Do.** Add terrain elevation for the 65 nm area as a small pre-sampled grid,
committed and loaded once (no network at import). Compare
`altitude − terrain` against AGL limits. Keep abstaining where terrain is unknown.

**Done when.** A fixture aircraft below an AGL floor doesn't fire and one above it
does; a test covers the grid edge (outside it → abstain).

### NFZ-12L — Grade confidence instead of 0 or 1

**Files:** `logic/scoring.py`

**Why.** `raw_model_confidence = float(confirmed)`: 1.0 only for an active zone
with the aircraft fully inside, otherwise 0.0. Every detection in the real-traffic
replay was 0.0. The syllabus (§6) says the detector supplies *detector-level
uncertainty* for TCE/CAATS; a column of zeros gives it nothing to weigh.

**Do.** Derive confidence from what is actually uncertain: activation unknown,
buffered-only containment (position error vs distance to the boundary), altitude
source (geometric vs barometric). Keep `anomaly_score` meaning "how bad" and
confidence meaning "how sure".

**Done when.** Tests show the ordering across those cases; severity is unchanged.

### NFZ-12M — Apply `airspace.include_types`

**Files:** `__init__.py` (`build_detector`) or `adapter.py`

**Why.** The config lists `include_types`, and the loader's docstring says
filtering is the caller's job, but no caller does it, so editing the list changes
nothing.

**Do.** Filter zones by `include_types` where they are loaded, so for example MOAs
can be dropped from alerting by config alone.

**Done when.** A test where removing `MOA` from the list removes the MOA zones.

---

## Track B · Live validation

These are Part 4 of `docs/live_integration/TEAM_NO_FLY_ZONE.md` (E1–E4), our
team's assigned validation work.

### NFZ-12N — End-to-end tests in the repo (E1/E2)

**Files:** new `tests/air/detectors/no_fly_zone/test_nfz_end_to_end.py`

**Why.** The chain observations → runner → `no_fly_zone_detections` has been
proven against a real Postgres, but only with a script that isn't in the repo.
Nothing in the suite would catch a regression.

**Do.** A test that seeds `observations` with the crossings fixture
(`fixtures/tracks/lynchburg_crossings.csv`) and runs
`run_live(..., once=True)` (E1); and a test that drives two or more ticks with an
incursion crossing a window edge and asserts **one** row (E2). Use a throwaway
database and skip when `SKYWATCH_TEST_DSN` isn't set, like the real-Postgres test
in `test_nfz_live.py`. Pin the fixture zones (`klyh-150nm.geojson`). Tim has
the working script to start from.

**Done when.** Both pass locally against `docker compose up -d db`.

### NFZ-12O — Live smoke test and behaviour note (E3/E4)

**Blocked on:** #121 merged (without it there is no altitude in live data).

**Why.** Everything we know about detection rates comes from a recorded hour.
The spoofing team's version of this is `docs/spoofing/LIVE_SMOKE.md` (#124),
a good model.

**Do.** Run the poller and the NFZ runner continuously for at least a few hours.
Report: detections per hour by zone, how many are one aircraft split into
several episodes, the share of reports skipped as `bad_input`, and the runner's
`lag_s` / `duration_s` from `docker logs`. Capture one or two real incursions as
fixtures. Note whether `max_gap_sec` (30 s) holds at the feed's rate (it did on
the replay: 40 vs 42 detections, one split).

**Done when.** A short `docs/no_fly_zone/LIVE_SMOKE.md` with the numbers, and any
captured fixtures committed with a test.

### NFZ-12P — Run the database tests in CI

**Files:** `.github/workflows/tests.yml`

**Why.** CI has no Postgres, so every test that needs one (`test_nfz_live.py`'s
real-database test, persistence, the reader SQL, NFZ-12N) is skipped there.

**Do.** Add a `timescale/timescaledb-ha:pg14` service (the same image as
`docker-compose.yml`), load `db/schema/*.sql`, set `SKYWATCH_TEST_DSN`.

**Done when.** CI shows those tests running, not skipped.

---

## Track C · Runner (Spine C)

### NFZ-12K — Skip reasons in the heartbeat

**Files:** `air/live/runner.py`, `docs/RUN_PIPELINE.md`

**Why.** Week 12's exit criterion is "each detector fails safely". NFZ counts why
every report left without a detection (`exit_counts`: `no_candidate`,
`vertical_clear`, `bad_input`, …), but the heartbeat (`detector_runs.counts`)
only stores observations and detections. A detector that can't see altitude and
a quiet sky look identical: `SUCCESS`, 0. That is exactly what live data did
before #121.

**Do.** Add the per-tick change in `exit_counts` to the heartbeat counts when the
detector has them (only NFZ does today; keep it optional). A `bad_input` share
near 100% is the alarm.

**Done when.** A runner test shows the counts in `finish_run`, and
`RUN_PIPELINE.md` has a query that shows them.

### NFZ-12Q — Fail fast on misconfiguration

**Files:** `air/live/runner.py`, `scripts/run_live_detector.py`

**Why** (from Nate's `WEEK12_TODO.md`). A missing detection table isn't noticed
until the first real detection, and `load_extra_columns` silently returns `None`
if the module or function name is wrong, dropping that detector's columns.

**Do.** At startup, check the table exists and the mapper loaded; log what loaded;
exit with a clear message otherwise.

**Done when.** Tests for both failure cases.

### NFZ-12R — One runner per detector

**Files:** `air/live/runner.py`

**Why** (from Nate's `WEEK12_TODO.md`). Two copies of one detector's runner
(a crash-loop overlap, a tick outliving its interval) can run at once. Results
stay correct (cursor `GREATEST` plus dedup) but work is wasted.

**Do.** Take a Postgres advisory lock keyed on `detector_id` for the life of the
runner; a second copy logs and exits.

**Done when.** A test with two lock attempts on the same id.

---

## Track D · Demo

### NFZ-12H — Live incursions on the dashboard

**Files:** `air/detectors/no_fly_zone/dashboard/app.py`

**Why.** The Streamlit dashboard reads `detections.jsonl` and Parquet files, the
offline outputs. The live pipeline writes `no_fly_zone_detections`.

**Do.** Add a source option that reads the table (`SKYWATCH_DB_DSN`), showing open
incursions (no end time) differently from closed ones, with the 15 zone polygons
from `klyh-local-faa.geojson` (R-6602 and P-56 visually distinct from MOAs).

**Done when.** Pointed at the local DB, it shows the rows the runner wrote.

---

## Done this week

| ID | What | PR |
|---|---|---|
| — | NFZ table mapper (`live.py`); runner stopped flushing every tick (one crossing was one row per tick) | #118 |
| 12B | Reports arriving late were dropped (one watermark for all aircraft); now per aircraft | #119 |
| 12C | Real FAA zones in the live runner, scoped to Lynchburg plus P-56 | #120 |
| 12I | Runner: catches up after downtime, survives errors, clean SIGTERM shutdown, a log line per tick | #122 |
| 12J | Zone lookup 52× faster (609 s → 11.7 s per replayed hour on 52 zones) | #122 |
| 12A | Live data arrived without altitude: confirmed on live data; fix in review | #121 (Will) |
| 12G | Stale spine test; fix in review | #116 (Will) |
| 12F | Report-rate tuning: measured on the replay, settings hold; folded into 12O | — |

---

## Reference

**Real-traffic replay** (`data/lynchburg_adsb.csv`, one hour, 284,249 reports, 914 aircraft):

| Zones | Detections | Notes |
|---|---|---|
| All 52 FAA zones within 150 nm | 42 | 39 from zones 100+ nm away, mostly airliners at cruise over Chesapeake Bay restricted areas |
| 15 local zones (current) | 2 | Both Evers South MOA, LOW, confidence 0 |

**Useful commands** (full guide: `docs/RUN_PIPELINE.md`)

```bash
# NFZ tests
pytest tests/air/detectors/no_fly_zone -q

# Live: poller + all runners, then follow NFZ
docker compose --profile poller --profile runners up -d --build
docker logs --tail 20 -f skywatch-no-fly-zone-runner

# Latest NFZ rows
docker exec skywatch-db psql -U skywatch -d skywatch -x -c "SELECT entity_id, zone_id, zone_type, severity, confidence, temporal_bounds_start, temporal_bounds_end FROM no_fly_zone_detections ORDER BY last_detected_at DESC LIMIT 5;"

# Regenerate the local zones (each 8-week FAA cycle; needs internet)
python scripts/make_faa_airspace.py --radius-nm 65 --also "P-56" --out air/detectors/no_fly_zone/fixtures/airspace/klyh-local-faa.geojson
```
