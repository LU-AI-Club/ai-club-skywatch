# Fixtures — the shared test corpus

Small, hand-built or captured ADS-B samples that lanes test against. These are
**committed** (unlike raw data dumps, which `.gitignore` excludes) because they
are the shared ground truth every lane and the CI run depend on.

Each fixture is a JSON list of observation dicts matching the fields of
[`AdsbObservation`](../models/observation.py). Extra keys prefixed with `_`
(e.g. `_label`, `_note`) are annotations — `AdsbObservation.from_dict` ignores
unknown keys, so they are safe to include.

`example_altitude.json` shows the format. Each detector team owns its own
positive (should fire) and negative (benign look-alike) fixtures — that is
Lane 1 (EDA + Fixtures).
