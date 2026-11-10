# No-Fly-Zone — Week 12 tickets

Per Nate's Week 12 email: get the live pipeline running, then improve detectors
for **false positives** and **inefficiencies**. These came out of running the
no-fly-zone lane end to end (reader → detector → `no_fly_zone_detections`) and
reading what the live path actually does, not from looking for things to change.

Branch off `main`, PR into `main`. Every ticket finishes with a fixture test
(`docs/DETECTOR_PLAYBOOK.md`); no live services in tests.

**Already fixed in the PR that adds this file** (not tickets):

- `air/detectors/no_fly_zone/live.py` fills `zone_id`, `zone_name` and `zone_type`,
  so NFZ detections can be stored at all (`zone_id` and `zone_type` are NOT NULL).
- The live runner called `flush()` every tick. For NFZ that closed each incursion
  every 30 s and restarted it as a new row, so one crossing became one row per
  tick. `flush()` now runs only at the end of a stream (`--once`). Spine C is ours,
  so this was ours to fix.
- `docs/RUN_PIPELINE.md` now counts and shows `no_fly_zone_detections`.

| Ticket | What | Kind | Size | Needs live data |
|---|---|---|---|---|
| NFZ-12A | Confirm the live payload carries altitude | Blocking check | S | Yes |
| NFZ-12B | Late-arriving reports are dropped | Missed incursions | M | No |
| NFZ-12C | Real FAA airspace in the live runner | Coverage | M | No |
| NFZ-12D | 46 of 52 real zones have UNKNOWN activation | Precision | M | No |
| NFZ-12E | 17 of 52 real zones can never fire (AGL floors) | Coverage | M | No |
| NFZ-12F | Measure episodes and cost at the live rate | Tuning / efficiency | M | Yes |
| NFZ-12G | Fix the stale spine test so `main` is green | Hygiene | S | No |
| NFZ-12H | Point the dashboard at the live table | Demo | M | No |
| NFZ-12I | Live runner: catch-up, resilience, shutdown, logging | Pipeline | M | No — **fixed** |
| NFZ-12J | Zone lookup re-serialized every zone per report | Efficiency | S | No — **fixed** |
| NFZ-12K | Put skip reasons in the heartbeat ("fail safely") | Pipeline / eval | S | No |
| NFZ-12L | Confidence is only ever 0 or 1 | Output quality | M | No |
| NFZ-12M | `airspace.include_types` is never applied | Config | S | No |

**Measured on real traffic** (one hour of the Lynchburg capture, 284,249 reports,
914 aircraft), which re-ranked these: with all 52 FAA zones within 150 nm, 39 of
42 detections came from zones 100+ nm away, mostly airliners at cruise. With the
15 local zones (#120: within 65 nm plus P-56), 2 detections, both Evers South
MOA, both LOW with confidence 0. So for the local set, **12E and 12D now matter
most**: they decide whether a nearby zone can fire at all, and at what severity.

---

## NFZ-12A — Does the live payload reach us with altitude? *(check first)*

**Owner:** ___ · same question as the spoofing team's SPOOF-12C; do it once, together.

`scripts/poll_adsb_feed.py` stores the SENTINEL envelope verbatim, and
`docs/RUN_PIPELINE.md` says the readsb fields sit nested under `payload.payload`.
`air/live/payload.py` reads them flat (`payload["altitude_ft"]`), the shape the
CSV loader writes. If both are true, every live observation reaches us with
`altitude_ft = alt_geom_ft = None`.

For no-fly-zone that is total: `geo/altitude.py` abstains with `BAD_INPUT` when
both altitudes are missing, so **every** aircraft exits before scoring, every run
reports `SUCCESS` with 0 detections, and it looks exactly like a quiet sky.
Squawk, callsign and NIC/NACp go too, which silences the context signals.

**Do:** with the poller running, check one real row:

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -c "SELECT payload ? 'altitude_ft' AS flat_altitude, payload->'payload' ? 'alt_baro' AS nested_alt_baro FROM observations WHERE domain='air' ORDER BY observed_at DESC LIMIT 5;"
```

If it is nested, the fix belongs in spine A (`air/live/payload.py`, spoofing
team), not in our adapter, so all three detectors get it.

**Done when:** a live row read through `observation_from_row` has a non-null
altitude, with a test on a captured envelope.

---

## NFZ-12B — Reports that land late are dropped *(missed incursions)*

**Status: fixed** in branch `nfz/late-reports`: the watermark is per aircraft,
with `sampling.seen_retention_sec` bounding memory. Kept here for the reasoning.

**Owner:** Tim · `air/detectors/no_fly_zone/adapter.py`

The adapter skips any report at or before `_watermark`, which is **one timestamp
for all aircraft**. The poller writes every 10 s and the runner ticks every 30 s,
so rows whose `observed_at` is a few seconds old routinely arrive after a tick has
already processed a newer report from some other aircraft. Those rows are
skipped forever.

Reproduced: aircraft A (outside any zone) processed up to t=10; aircraft B's five
reports inside P-901 at t=4..8 arrive in the next window. Result: **0 detections,
7 skipped**. The same five reports in order: **1 detection**.

**Do:** keep the watermark per aircraft (`icao24 → newest timestamp`), so overlap
is still deduplicated but one aircraft's late report is not judged against
another's clock. Check `close_silent` still uses a sensible "now".

**Done when:** a fixture test with exactly that interleaving produces the
incursion, and `test_nfz_adapter.py` plus `test_nfz_live.py` stay green.

---

## NFZ-12C — Use real FAA airspace in the live runner

**Owner:** Tim · branch `nfz/faa-airspace` (one commit, Will, Oct 27, **no PR yet**)

The live runner loads `airspace.fixture_path`, which is still three hand-built
test zones (P-901, one TFR, one MOA). `scripts/make_faa_airspace.py` on that
branch builds the real 52 zones within 150 nm of KLYH from the FAA AIS feature
service; it merges cleanly onto `main`.

**Do:** open the PR for `nfz/faa-airspace`. Then make the live runner load the
generated file without breaking the test suite, which pins the fixture zones in
55 assertions (for example, a `build_live_detector` override for the live path
only). The 1 MB file is generated, not committed, so decide how the runner image
gets it.

**Done when:** a `--once` run on the live DB loads 52 zones, and tests still pass.

---

## NFZ-12D — Most real zones have UNKNOWN activation *(precision)*

**Owner:** ___ · `logic/activation.py`, `scripts/make_faa_airspace.py`

FAA `TIMESOFUSE` is prose. Only `CONTINUOUS` is parsed as always active, so 46 of
52 real zones come out SCHEDULED or NOTAM with no active windows, which is
UNKNOWN activation, capped at LOW severity (`severity.unknown_activation_cap`).
An incursion into a MOA that is cold today looks the same as one that is hot.

**Do:** parse the common clock-time forms (e.g. `0700-2200 LOCAL MON-FRI`) into
`active_windows`; leave anything that is not parseable as UNKNOWN rather than guessing.

**Done when:** a test per parsed form, and a count of how many of the 52 now have
known activation.

**Local set (#120):** every local MOA is SCHEDULED and R-6602 is NOTAM, so every
local zone except P-56 is UNKNOWN and every local detection is capped at LOW. Do
the local zones first.

---

## NFZ-12E — Zones with AGL floors can never fire *(coverage)*

**Owner:** ___ · `geo/altitude.py`

A non-zero `SFC` floor (Farmville MOA: 300 FT SFC) means above ground, so it maps
to `Datum.AGL`, and the vertical check abstains on AGL because there is no
terrain model. 17 of 52 real zones are in this position: they can never alert.

**Do:** add a terrain elevation lookup (e.g. a small pre-sampled grid for the
150 nm scope, loaded once, no network at import) and compare AGL floors against
altitude minus terrain. Keep abstaining where terrain is unknown.

**Done when:** a fixture aircraft below an AGL floor does not fire and one above
it does.

**Local set (#120): 7 of the 13 Lynchburg-area zones have AGL floors** (Farmville
MOA x3, Evers Low and East, Barfoot 1 and 2), so more than half the nearby
airspace cannot alert today. On the replay, 1,645 reports exited `bad_input`,
mostly here. A grid covering 65 nm is far smaller than one for 150 nm.

---

## NFZ-12F — Measure episodes and cost at the live rate *(tuning / efficiency)*

**Owner:** ___ · `configs/detectors/no_fly_zone.yaml`, runner settings

The config was written for 1 Hz from our own receiver (`target_hz: 1.0`). The
live feed is polled every 10 s, and the runner reads a 300 s window every 30 s,
so each row is read about ten times. `max_gap_sec: 30` and
`clear_observations_to_close: 2` have never been checked against that rate.

**Measured, lower priority now:** thinning the capture to one report per aircraft
per 10 s (the feed's rate) gave 40 detections against 42 at 1 Hz, with one
aircraft-zone pair split, so `max_gap_sec: 30` holds. Do **not** shrink `window_s`:
the feed returns positions up to 5 minutes old (`ADSB_POSITIONS_FEED_GUIDE.md`),
and the reader filters on `observed_at`, so a row older than the window start
when it arrives is never read.

**Do:** after a few hours of live data, confirm: incursions per hour, split
episodes, `skipped_reports`, and the per-tick `lag_s`/`duration_s` the runner now
logs (NFZ-12I).

**Done when:** a short note in `docs/no_fly_zone/` with the numbers and any
config change it justifies.

---

## NFZ-12G — Make `main` green again *(good first ticket)*

**Owner:** ___ · `tests/air/live/test_live_spine.py`

`test_stubs_raise_until_owning_teams_implement_them` fails on `main`: it asserts
the spine components still raise `NotImplementedError`, and they have since been
implemented. It is the only failing test in the suite.

**Do:** replace it with a check that the spine's public entry points exist with the
frozen signatures, or delete it with a one-line reason in the PR.

**Done when:** `pytest` on `main` has zero failures.

---

## NFZ-12H — Show live incursions on the dashboard *(for the Xenith demo)*

**Owner:** ___ · `air/detectors/no_fly_zone/dashboard/app.py`

The Streamlit dashboard reads `detections.jsonl` and Parquet files, the offline
outputs. The live pipeline writes `no_fly_zone_detections`.

**Do:** add a source option that reads the table (`SKYWATCH_DB_DSN`), showing open
incursions (no end time) differently from closed ones, with the zone polygons.

**Done when:** pointing it at the local DB shows the rows the runner wrote.

---

## NFZ-12I — Live runner: catch-up, resilience, shutdown, logging

**Status: fixed** in branch `nfz/runner-hardening` (Spine C is ours). What
`SPINE_PLAN.md` asked for and the runner did not do:

- **Fell behind forever.** It slept the full 30 s after every tick, losing the
  tick's own run time each time: about 24 min behind live after a day at 0.5 s
  ticks, and never caught up after a restart. Now it sleeps only what is left of
  the interval and runs windows back to back when behind: lag stays at about one
  tick's run time, and a runner restarted an hour behind is current in ~4 min.
- **Died on any error.** A DB hiccup raised out of the loop, the container
  restarted, and NFZ's open incursions (held in memory) were lost, leaving rows
  OPEN forever. Now a failed tick is logged and retried with back-off (doubling,
  capped at 300 s), the detector keeps its state, and detections that could not
  be stored are carried to the next tick.
- **Ignored `docker compose down`.** As PID 1 with no SIGTERM handler, it was
  killed after the 10 s grace period, mid-tick. Now it finishes the tick, flushes
  open incursions so none stay OPEN, and exits.
- **Printed nothing.** Now one line per tick in `docker logs`:
  `tick detector=… status=SUCCESS window_end=… lag_s=… duration_s=… observations=… detections=… inserted=… updated=… skipped=…`

---

## NFZ-12J — Zone lookup re-serialized every zone on every report

**Status: fixed** in branch `nfz/runner-hardening`. The H3 prefilter cached each
zone's cells keyed on the zone's WKB bytes, so it serialized every zone outline
(about 45,000 points for the 52 FAA zones) for every position report just to
build the key: 85% of run time. Keyed on the geometry object now. One hour of
traffic on 52 zones: **609 s → 11.7 s**, same 42 detections and exit counts.

---

## NFZ-12K — Put skip reasons in the heartbeat *(Week 12: "each detector fails safely")*

**Owner:** ___ · `air/live/runner.py` (heartbeat counts), `adapter.py`

The detector counts why every report left without a detection (`exit_counts`:
`no_candidate`, `vertical_clear`, `bad_input`, …), but the live heartbeat
(`detector_runs.counts`) only has observations and detections. So a detector that
is blind (no altitude, NFZ-12A) and a quiet sky look identical: `SUCCESS`, 0.

**Do:** add the per-tick change in `exit_counts` to the heartbeat counts when the
detector has them. A `bad_input` share near 100% is the alarm.

**Done when:** a runner test shows the counts, and `RUN_PIPELINE.md` has the query.

---

## NFZ-12L — Confidence is only ever 0 or 1 *(output quality)*

**Owner:** ___ · `logic/scoring.py`

`raw_model_confidence = float(confirmed)`: 1.0 only for an active zone with the
aircraft fully inside, otherwise 0.0. Every real detection in the replay was 0.0.
The syllabus (§6) says the detector supplies *detector-level uncertainty* for
TCE/CAATS, and a column of zeros gives it nothing to weigh.

**Do:** grade it from what is actually uncertain: activation unknown, buffered-only
containment (position error vs distance to the boundary), altitude source
(geometric vs barometric). Keep `anomaly_score` as "how bad", confidence as "how sure".

**Done when:** tests show confidence ordering across those cases; no change to severity.

---

## NFZ-12M — `airspace.include_types` is never applied *(config)*

**Owner:** ___ · `__init__.py` / `adapter.py`

The config lists `include_types`, and the loader says filtering is the caller's
job, but no caller does it, so editing the list changes nothing. Apply it where
zones are loaded, so e.g. MOAs (legal to fly through) can be dropped from alerting
by config. **Done when:** a test where removing `MOA` drops the MOA zones.

---

Not ours, but noticed: if `sentinel-ca.crt` is ever missing, Docker mounts an
empty *folder* in its place and the poller fails TLS confusingly. Nate's
`docs/WEEK12_TODO.md` lists the runner resilience and catch-up items (12I) and
two more Spine C ones worth taking: fail fast on a missing table or mapper, and a
single-instance guard.
Restart still loses NFZ's in-memory state after a *crash* (12I covers clean stops
and DB errors); persisting open episodes is a future option.
