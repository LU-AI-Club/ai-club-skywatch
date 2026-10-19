# load_csv

**What it does:** reads a whole ADS-B CSV into a list of `AdsbObservation`
records.
**File:** air/normalizers/lynchburg_csv.py
**Inputs:** a path to a CSV file.
**Output:** a list of `AdsbObservation`.
**How it's tested:** on a small written-out file it keeps the good rows and
skips relayed ones and ones missing a position; an empty file gives an empty
list.
**Gotchas:** unusable rows are skipped silently. If a future change drops most
of the file, nothing here will complain - the row count is worth checking.

## Reading lazily

The real file is 70 MB. `iter_observations` streams it row by row with
`csv.DictReader`, and `load_csv` wraps that when a list is wanted. Nothing ever
holds the raw text of the whole file at once.

## On the real data

`load_csv("data/lynchburg_adsb.csv")` returns **284,337 observations from 909
aircraft in under 10 seconds**. The 139 skipped rows are the relayed ones
`is_direct_adsb` rejects; no row is dropped for being broken.
