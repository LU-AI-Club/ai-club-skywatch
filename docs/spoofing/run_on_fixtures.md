# run_on_fixtures

**What it does:** Runs a detector over every fixture file in a folder and
reports, per file, whether it should have fired and whether it actually did.

**File:** scripts/evaluate_spoofing.py

**Inputs:**
- `detector` — anything with a `.detect_observations(observations) -> detections` method
- `fixture_folder` — path (str or Path) to a folder of fixture JSON files, e.g. `air/fixtures/spoofing/`

**Output:** list of dicts, one per fixture file:
- `fixture_name` (str) — the file name
- `expected_positive` (bool) — should this fixture have produced a detection?
- `expected_gate` (str) — which rule it should have tripped, e.g. `"teleport_v1"`
- `detections` (list) — whatever the detector actually returned
- `fired` (bool) — `True` if `detections` is non-empty

**How it's tested:** No real spoofing detector exists yet, so
`tests/air/detectors/spoofing/test_spoofing_run_on_fixtures.py` uses two fake stand-ins instead —
one that never returns a detection, one that always returns one. Against
both, it checks: every `.json` fixture file gets exactly one result; the
`.csv` and `.md` files in the folder are correctly skipped; the expected
positive/negative label and gate name are read correctly off real fixtures
(`pos_teleport.json`, `neg_tailwind_cruise.json`, `clean_track.json`); and
`fired`/`detections` match whichever fake detector was used.

**Gotchas:**
- The right answer comes from each row's `_label` field (`"positive:<gate>"`,
  `"negative:<gate>"`, or `"ok"`). Fixtures only label the specific rows a
  positive case touches — most rows in a `pos_*.json` file are still `"ok"` —
  so this scans every row and lets a `"positive:..."` tag anywhere in the
  file win.
- A fixture with no positive or negative tag at all (e.g. `clean_track.json`,
  which is 100% `"ok"`) reports `expected_gate` as `"unlabeled"`.
- Only `*.json` files in the folder are read; the reference `.csv` files and
  `README.md` are ignored.
- This only checks the wiring (files load, labels parse, detector output is
  carried through) — it can't check real detection accuracy until a real
  spoofing detector exists to run it against.
