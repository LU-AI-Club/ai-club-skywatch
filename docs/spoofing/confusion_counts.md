# confusion_counts

**What it does:** Takes the results from `run_on_fixtures` and counts, for each
rule, how many catches, false alarms, misses and correct quiets there were.

**File:** scripts/evaluate_spoofing.py

**Inputs:**
- `results` — list of dicts, exactly what `run_on_fixtures` returns. Only three
  keys are read: `expected_gate` (str), `expected_positive` (bool), `fired` (bool).

**Output:** dict of rule name -> dict of four counts (ints, number of fixture files):
- `tp` — catch: the fixture should have fired, and did
- `fn` — miss: the fixture should have fired, and did not
- `fp` — false alarm: the fixture should not have fired, but did
- `tn` — correct quiet: the fixture should not have fired, and did not

Example: `{"teleport_v1": {"tp": 1, "fp": 0, "fn": 0, "tn": 1}}`

**How it's tested:** `tests/air/detectors/spoofing/test_spoofing_confusion_counts.py`.
A made-up one-item list checks each of the four boxes on its own (a catch, a
miss, a false alarm, a correct quiet). A made-up five-item list with two rules
checks the rules are counted separately. An empty list gives an empty dict.
Then it runs on the real fixtures with two fake detectors: one that never
fires (only misses and correct quiets, no catches or false alarms) and one
that always fires (only catches and false alarms, and the counts add up to
the number of fixture files).

**Gotchas:**
- It counts fixture files, not individual detections. A file that fires ten
  times is still one catch or one false alarm.
- It only looks at whether the detector fired at all, not which rule fired. If
  `pos_teleport.json` fires because of the turn-rate rule, that still counts
  as a catch for `teleport_v1`.
- Each file is counted under its `expected_gate`, so the rule names are
  whatever the fixture labels say. Fixtures with no label (like
  `clean_track.json`) are grouped under `"unlabeled"`.
- A rule only appears in the output if at least one fixture is labelled with it.
