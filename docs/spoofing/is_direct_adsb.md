# is_direct_adsb

**What it does:** keeps only messages our receiver heard straight from the
aircraft.
**File:** air/normalizers/lynchburg_csv.py
**Inputs:** one CSV row, as a mapping.
**Output:** True or False.
**How it's tested:** `adsb_icao` passes; `adsr_icao`, `tisb_other`, an unknown
value and a blank all fail; a row with no `t` column fails rather than raising.
**Gotchas:** this is a filter, not a detection. A relayed message is not
suspicious, it is simply measured differently.

## Why we drop the rest

Column `t` carries the source type:

| Value | What it is | Keep? |
|---|---|---|
| `adsb_icao` | Direct reception from the aircraft | yes |
| `adsr_icao` | Rebroadcast on a different link by a ground station | no |
| `tisb_other` | Assembled by a ground station, often from radar | no |

Relayed and ground-derived positions carry different timing and position
semantics than a direct reception, so they would trip the kinematic gates
without anything actually being wrong.

In `data/lynchburg_adsb.csv` this drops 139 rows out of 284,476 - 0.05% of the
file, but potentially a large share of the false positives.
