# readsb/tar1090 CSV → `AdsbObservation` column map

How `adsb_csv.py` maps the raw columns of `data/lynchburg_adsb.csv` (a
readsb/tar1090 field dump) onto the air-domain input contract,
[`AdsbObservation`](../models/observation.py).

**The export is already in the contract's units** (feet, knots, fpm, degrees),
so the normalizer does **no unit conversion** — it only parses, cleans, and
drops untrustworthy rows.

## Mapped fields

| `AdsbObservation` field | CSV column | Meaning / notes |
|---|---|---|
| `icao24` | `h` | 24-bit ICAO hex. Blank → row skipped. |
| `observed_at` | `timestamp` | Canonical position time, e.g. `2026-09-01 00:00:00.014000+00:00`. `AdsbObservation` parses it to tz-aware UTC. (`ra` carries the same instant in `...Z` form — ignored as a duplicate.) |
| `latitude` | `la` | WGS84 degrees. Blank/garbled → row skipped (position is required). |
| `longitude` | `lo` | WGS84 degrees. Blank/garbled → row skipped. |
| `altitude_ft` | `ab` | Barometric altitude, feet. |
| `ground_speed_kt` | `gs` | Knots. |
| `track_deg` | `tr` | Course over ground, 0–360°. (`th` true-heading is empty in this feed.) |
| `vertical_rate_fpm` | `br` → `gr` | Barometric vertical rate (fpm); falls back to geometric rate `gr` when `br` is empty. |
| `nic` | `n` | Navigation Integrity Category (0–11). |
| `nacp` | `np` | Navigation Accuracy Category – Position (0–11). |
| `squawk` | `sq` | 4-digit transponder code, kept as a string (e.g. `7700`). |
| `callsign` | `f` | Flight id; ADS-B space-padding is stripped. |
| `receiver_id` | — | Not present in this single-receiver feed. Defaults to `None`; the runner may pass `receiver_id="lynchburg"`. |

## Ignored columns (intentionally)

Present in the CSV but **not** in the `AdsbObservation` contract, so the
normalizer skips them. Listed here so nobody wonders whether they were missed:

`c` (emitter category), `d` (description), `ag` (alt_geom), `gv`, `rc` (radius
of containment), `s` (SIL), `st` (SIL type), `v` (ADS-B version), `nb`
(NIC-baro), `nv` (NAC-v), `nq` (nav QNH), `nam`/`naf` (nav selected altitudes),
`nh` (nav heading), `nm` (nav modes), `em` (emergency), `ra` (duplicate time),
`rs`, `sp`, `a`, `spi`, `wd`/`ws` (wind), `oat`/`tat` (temps), `rds`, `rdi`,
`sda`, `ct`, `gpb`, `sn`, `og` (on-ground flag), `t` (message type), `link`,
`m`, `i`, `mh`, `trr`, `ro`.

If a detector later needs one of these (e.g. `s`/`np` for a receiver-quality
false-positive gate, or `og` to treat on-ground aircraft specially), add it to
`AdsbObservation` first — one PR that changes the contract, updates this
normalizer, and is announced so downstream owners rebase.

## Skip (abstain) rules

A row is **dropped** only when it is unusable:
1. Blank `h` (no identity).
2. Missing or out-of-range `la`/`lo` (no position).
3. An unparseable timestamp / coordinate that makes `AdsbObservation` raise.

Any *other* bad field (e.g. a non-numeric `gs` or `br`) becomes `None` and the
row is still emitted — one malformed secondary field never discards a good
position.

## How this map was derived

Columns were aligned against the readsb/tar1090 field schema and sanity-checked
on `data/lynchburg_adsb.csv`: `ab` holds plausible feet (4,850 / 35,975), `gs`
plausible knots, `tr` stays within 0–360, `nq` reads like a QNH pressure
(~1018 hPa), and the `timestamp` column is monotonic apart from ~340 rows of
receiver jitter. Re-verify if a different readsb export (different column set or
order) is introduced.
