# fixtures/

Hand-built test data. **None of this is real airspace** - do not treat the
polygons as authoritative and do not fly by them. They exist so every stream
has something deterministic to test against before the real FAA SUA feed is
wired up.

## airspace/klyh-150nm.geojson

Three zones near KLYH (37.3267, -79.2004), chosen to exercise the three
activation paths:

| zone_id | type | altitude band | activation |
|---|---|---|---|
| `P-901` | PROHIBITED | SFC - 18000 MSL | `ALWAYS` |
| `TFR-6/1234` | TFR | SFC - 5000 MSL | `WINDOW` 2026-09-22T19:00Z -> 2026-09-23T01:30Z |
| `LYNCHBURG-MOA` | MOA | 8000 MSL - FL180 | `SCHEDULED` |

## tracks/klyh_mixed.json

Five `AircraftState` rows. Each carries two annotation keys, `_label` and
`_expect`, that are **not** `AircraftState` fields - stream A must ignore
unknown keys when loading. `_expect` is what the full pipeline should conclude,
so tests can assert against it.

| row | what it is | expected |
|---|---|---|
| `fixture-1` | inside P-901, below the ceiling | detection |
| `fixture-2` | over P-901 at FL350 | exit `vertical_clear` |
| `fixture-3` | inside the TFR, window open | detection |
| `fixture-4` | same spot, window shut | exit `zone_inactive` |
| `fixture-5` | clear of everything | exit `no_candidate` |

## tracks/lynchburg_crossings.csv

The **real** raw rows (35, with the file's full readsb header) of two aircraft
crossing fixture zone P-901, cut from `data/lynchburg_adsb.csv`. The aircraft
and positions are real; the zone is not.

| aircraft | what it is | per-report | episodes |
|---|---|---|---|
| `a89076` (PDT5877) | 41 s inside at ~16,500 ft; squawk 2240 appears 14 s in | 19 | 1, HIGH, peak 0.909 |
| `ac8438` (N90508) | buffer-only, then inside, reporting every ~6 s | 2 | 1, HIGH |

`tests/air/detectors/no_fly_zone/test_nfz_episodes.py` pins those numbers.

## What is still missing

No fixture yet covers `on_ground`, `bad_input` (both altitudes null) or
`buffered_only` (just outside the fence with a poor NIC). Whoever owns the
false-positive lane should add them.

## Local FAA schedules and terrain

`airspace/klyh-local-faa.geojson` carries parsed recurring schedules in
`America/New_York`. The Farmville, Evers, Barfoot, and R-6602A schedule
phrasings are active during their published windows; outside windows that
allow additional NOTAM activation, status stays unknown. Thirteen of the 15
local zones now have known activation.

`terrain/klyh-65nm.json` is a committed USGS 3DEP elevation grid covering the
65 nm KLYH operating area. Its approximately 2 km cells are stored in feet
MSL and bilinearly interpolated for AGL floors. It is loaded once at detector
construction; the detector makes no network requests. Where the grid has
no value (outside it, or a no-data cell) an AGL floor is placed with the
area-wide bound `geometry.off_grid_terrain_ft` instead, and the report is
skipped only where that cannot decide. The grid stops at 38.435 N and
77.813 W, short of the zones: Evers East is 16% covered, Barfoot 1 54%, and
Evers Low 63%. Rebuilding it over lon -80.67..-77.72, lat 36.78..38.76 (the
bounds of the local zones) would cover all of them.
