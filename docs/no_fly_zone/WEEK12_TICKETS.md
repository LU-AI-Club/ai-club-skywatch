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

**Owner:** ___ · `air/detectors/no_fly_zone/adapter.py`

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

**Status: fixed** in branch `nfz/faa-airspace-live` (Will's generator plus the live
wiring): `build_live_detector` loads `airspace.live_path` when generated, else falls
back to the test zones with a warning. Kept here for the reasoning.

**Owner:** Tim, Will · originally branch `nfz/faa-airspace`

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

---

## NFZ-12F — Measure episodes and cost at the live rate *(tuning / efficiency)*

**Owner:** ___ · `configs/detectors/no_fly_zone.yaml`, runner settings

The config was written for 1 Hz from our own receiver (`target_hz: 1.0`). The
live feed is polled every 10 s, and the runner reads a 300 s window every 30 s,
so each row is read about ten times. `max_gap_sec: 30` and
`clear_observations_to_close: 2` have never been checked against that rate.

**Do:** after a few hours of live data, report: incursions per hour, how many are
one aircraft split into several episodes, `skipped_reports`, and tick duration.
Then decide whether `window_s` can shrink (the adapter already keeps state across
ticks, so the overlap mostly buys tolerance for late rows; see NFZ-12B).

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

Not ours, but noticed: `db/schema/005_detector_runs.sql` and `006_detector_runs.sql`
are identical (the spoofing team flagged this too in #117).
