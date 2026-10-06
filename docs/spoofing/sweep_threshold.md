# sweep_threshold

**What it does:** Tries one limit at many values and reports, for each value,
how many catches, false alarms and misses the detector got on the fixtures.

**File:** scripts/evaluate_spoofing.py

**Inputs:**
- `setting` — str, the name of the limit to change, e.g. `"teleport_kt"`
- `values` — list of numbers to try, in the units of that limit (knots for
  `teleport_kt`)
- `fixture_folder` — path (str or Path) to a folder of fixture JSON files, e.g.
  `air/fixtures/spoofing/`
- `make_detector` — a function that takes a dict like `{"teleport_kt": 800}`
  and returns a detector built with that setting. The detector is anything
  with a `.detect_observations(observations) -> detections` method.

**Output:** list of dicts, one row per value, in the order the values were given:
- `setting` (str) — the name of the limit
- `value` — the value tried on this row
- `tp`, `fp`, `fn`, `tn` (int) — catches, false alarms, misses and correct
  quiets, in number of fixture files, added up across every rule
- `precision`, `recall` (float 0.0–1.0, or `None`) — worked out from those totals

**How it's tested:** `tests/air/detectors/spoofing/test_spoofing_sweep_threshold.py`.
No real spoofing detector exists yet, so the test sweeps a fake one that fires
if any row reports a ground speed over the limit. On the real fixtures: a
limit of 1000 kt fires on nothing (0 catches, 8 misses, no precision); 500 kt
fires only on the 780 kt tailwind file (1 false alarm); 400 kt fires on every
positive and 5 negatives (8 catches, 5 false alarms). It also checks there is
one row per value in the order given, that lowering the limit never lowers
recall, that every row adds up to the 17 fixture files, that `make_detector`
is handed exactly `{setting: value}`, and that an empty list of values gives
an empty table.

**Gotchas:**
- The worksheet lists three inputs (setting, values, fixtures). This has a
  fourth, `make_detector`, because there is no real spoofing detector or
  merged `SpoofingConfig` to build one from yet. Once there is, it would be
  something like `lambda settings: SpoofingDetector(SpoofingConfig(**settings))`.
- It does not check that `setting` is a real limit name. A typo is only
  caught if `make_detector` complains about it.
- The counts are totals across every rule, not just the rule the limit
  belongs to. Sweeping `teleport_kt` still counts the turn-rate and other
  fixtures.
- It inherits the limits of `confusion_counts`: it counts files, and a file
  counts as caught if the detector fired at all, whichever rule fired.
- The detector is rebuilt and every fixture re-read for each value, so many
  values on a large folder will be slow.
