# load_wingbits_csv

**Author:** drafted for the loader lane · **File:** `air/normalizers/wingbits_csv.py`

## What it does

Reads a recorded Wingbits ADS-B CSV and returns `AdsbObservation` objects — the
shared input every detector consumes. Until this existed the detector had only
ever run on five hand-built scenarios; this is what lets it see real traffic.

It lives in `air/normalizers/` rather than in our detector folder because it is
shared enabling work: the spoofing and no-fly-zone teams can use it too.

## Inputs and outputs

| | Type | Units | Notes |
|---|---|---|---|
| in | `path` | — | The CSV file |
| in | `start`, `end` | tz-aware UTC datetimes | Optional time window |
| in | `bbox` | `(min_lat, min_lon, max_lat, max_lon)` | Optional box filter |
| out | `list[AdsbObservation]` | — | Sorted by time; unusable rows dropped |

## How it works

- **One column map, one place.** `COLUMN_MAP` translates the short Wingbits
  codes (`h`, `la`, `lo`, `ab` …) into `AdsbObservation` field names. Nothing
  downstream ever sees a raw column name.
- **Drop what cannot be used.** A row with no ICAO, timestamp or position is
  skipped. We do not guess a position.
- **Filter before building objects.** Time and bounding-box filters run on the
  DataFrame, so a five-minute slice costs a fraction of a full-hour load.
- **Convert `NaN` back to `None`.** pandas represents a blank cell as `NaN`,
  which is a float and therefore survives every `is not None` check. Without
  this conversion the detector's abstain rules would never fire.
- **Sort by time** so `group_tracks` and the interpolator get an ordered feed.

## Decisions and trade-offs

- **Barometric altitude (`ab`), never geometric (`ag`).** The file carries
  both. Mixing them across a pair invents vertical separation that does not
  exist. Row 0 of the sample shows the size of the problem: `ab` 4850 ft,
  `ag` 5200 ft — a 350 ft phantom gap on every comparison.
- **Load the whole file into memory.** 284k rows is about 5 seconds and fits
  comfortably. Streaming would be faster to first result but harder to read,
  and the detector needs the whole window anyway.

## What it does NOT handle

- **The `og` (on-ground) column is dropped.** `AdsbObservation` has no field
  for it, so `pairs.is_airborne` infers ground state from altitude and speed
  instead. Worth raising with the Technical Lead — the shared model probably
  should carry it, and every detector would benefit.
- **CSV only.** No Parquet, no JSON, no live feed.
- **No receiver-health or duplicate-ICAO handling.** An aircraft transmitting
  under two IDs is passed through as two aircraft.

## Tests

`tests/air/normalizers/test_wingbits_csv.py` — 11 tests against
`air/fixtures/wingbits_sample.csv` (50 rows), never the 70 MB file.
Positive: a known row maps to the right values, and `ab` is used rather than
`ag`. Negative: a row with a blank latitude is skipped, blanks come back as
`None` rather than `NaN`, and a time filter in the future returns nothing.

## First run on real data

One hour of Wingbits traffic within 200 miles of Lynchburg —
284,476 observations, 915 aircraft:

| | |
|---|---|
| Detections | 531 |
| HIGH | 24 |
| MEDIUM | 52 |
| LOW | 200 |
| INFO | 255 |
| Runtime | ~30 s |

These are **unreviewed**. Most are expected to be benign — aircraft sequenced
for the same runway are legitimately 3 nm apart. Judging them is the Week 7
evaluation lane (`docs/proximity/REVIEW_SHEET.md`).
