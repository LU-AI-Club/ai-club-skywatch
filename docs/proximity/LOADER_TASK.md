# Task: load the real Lynchburg data

**Owner:** Erik · **Due:** next meeting · **File to create:**
`air/normalizers/wingbits_csv.py`

## Why

Right now the detector can only run on the five made-up scenarios in
`air/fixtures/`. It has never seen real traffic. `data/lynchburg_adsb.csv` is
one hour of actual flights — 284,000 reports from 915 aircraft within 200 miles
of Lynchburg — and nothing in the repo can read it into the shape the detector
wants.

That's your job. Once it exists we point the detector at a real sky for the
first time, which is the Week 6 demo and the input to everything in Week 7.

This is also on the club's shared backlog ("ADS-B Normalizer"), so the other two
detector teams can use it. Put it in `air/normalizers/`, not in our detector
folder.

## What to build

```python
def load_wingbits_csv(
    path: str | Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    bbox: tuple[float, float, float, float] | None = None,
) -> list[AdsbObservation]:
```

Read the CSV, map the columns, return `AdsbObservation` objects. The optional
arguments let a caller take a slice instead of all 284k rows.

### Column mapping

The CSV uses short codes. These are the ones we need:

| CSV column | `AdsbObservation` field | Notes |
|---|---|---|
| `h` | `icao24` | lowercase hex |
| `timestamp` | `observed_at` | ISO-8601, already UTC |
| `la`, `lo` | `latitude`, `longitude` | degrees |
| `ab` | `altitude_ft` | **barometric**, not `ag` — see below |
| `gs` | `ground_speed_kt` | knots |
| `tr` | `track_deg` | degrees, 0–360 |
| `br` | `vertical_rate_fpm` | ft/min |
| `n` | `nic` | |
| `np` | `nacp` | |
| `f` | `callsign` | may be blank |

Ignore the other 43 columns.

### Things that will bite you

- **Use `ab` (barometric), never `ag` (geometric).** The file has both. Mixing
  them across a pair invents fake vertical separation. Pick one, be consistent.
- **Blank cells arrive as `NaN`, not `None`.** `AdsbObservation` expects `None`.
  Convert them, or every downstream check that asks "is this field missing?"
  breaks.
- **Rows with no lat, lon or timestamp can't be used** — skip them.
- **The `og` column (on ground) exists in the CSV but `AdsbObservation` has no
  field for it.** Drop it for now and say so in your write-up. Worth raising
  with Nate: the shared model probably should carry it.
- Use pandas to read, then build the objects. Don't parse the CSV by hand.

## Tests

`tests/air/normalizers/test_wingbits_csv.py`. Don't test against the 70 MB
file — commit a tiny sample instead:

```bash
head -50 data/lynchburg_adsb.csv > air/fixtures/wingbits_sample.csv
```

Cover at least:

- a known row maps to the right values (pick one, check it by hand)
- a row with a blank speed comes back as `None`, not `NaN`
- a row with no position is skipped
- the time filter returns fewer rows than no filter
- every returned object is an `AdsbObservation`

## When it works

```python
from air.normalizers.wingbits_csv import load_wingbits_csv
obs = load_wingbits_csv("data/lynchburg_adsb.csv")
print(len(obs), obs[0])
```

Then, once Manni's `detect_observations` lands, the whole detector runs on real
traffic. Nobody knows yet what it will say — finding out is next week.

## Submitting

Same loop as always: branch off `Proximity_Detector`, code plus tests plus a
write-up at `docs/proximity/wingbits_csv.md`, PR into `Proximity_Detector`.
