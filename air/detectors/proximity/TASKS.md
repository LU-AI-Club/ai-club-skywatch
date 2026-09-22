# Proximity detector — task board

The detector is a pipeline of small pure functions. Each one already has its
name, its inputs, its outputs, a docstring with the formula, and a set of tests
that prove it works. Your job is to replace one `raise NotImplementedError`
with a working body and turn your tests green.

```
raw observations
   │  tracks.interpolate_to_grid        ← Erik      (put everyone on the same 1-s clock)
   ▼
snapshot per second
   │  pairs.is_airborne / candidate_pairs ← CalebG  (nearby, flying, not stacked)
   ▼
pairs worth checking
   │  geometry.to_local_xy / velocity_xy / time_to_cpa / predicted_separation ← Manni
   ▼
PairGeometry (t_cpa, predicted separation)
   │  detector.severity_for / flag_pair  ← CalebK   (gates + threshold table)
   ▼
severity or None
   │  detector.to_detection              (done)
   ▼
Detection  ←  ProximityDetector.detect_observations ← Paul (wire it together)
```

## First time only: install the test tools

With your virtual environment active (your prompt shows `(.venv)`), from the
repo root:

```bash
pip install -e ".[dev,eda]"
```

`[dev]` is pytest, `[eda]` is pandas/matplotlib for notebooks. If you get
`pytest : The term 'pytest' is not recognized`, this is the step you missed.
Still stuck? `python -m pytest` works even when the `pytest` shortcut is not
on your PATH.

## See the board

```bash
pytest tests/air/detectors/proximity -q -rxX
```

`x` = still to do, `X` = implemented and passing, `F` = implemented but wrong.
Filter to your own: `pytest tests/air/detectors/proximity -q -rxX -k Erik` won't
work (owner is in the marker, not the name) — instead run your file directly,
the command is at the top of each test file.

## The loop (same for everyone)

```bash
# 1. Move to the team branch and get everyone else's latest work
git checkout Proximity_Detector
git pull

# 2. Make your own branch to work on, named after you and your function
git checkout -b proximity/<yourname>/<function>     # e.g. proximity/erik/interpolate

# 3. Open your file, find the line that says raise NotImplementedError,
#    and replace it with real code. Read the docstring above it first.

# 4. Run your own tests. Repeat steps 3-4 until they all pass.
pytest tests/air/detectors/proximity/test_proximity_<file>.py -q -rxX

# 5. In the test file, delete the @todo("YourName") line above every test
#    you now pass. That is how the board shows you are finished.

# 6. Write up what you built: copy the template, then fill it in
cp docs/proximity/_TEMPLATE.md docs/proximity/<function>.md

# 7. Check you broke nothing else in the repo
pytest -q

# 8. Save your work and send it to GitHub
git add -A
git commit -m "proximity: implement <function>"
git push -u origin proximity/<yourname>/<function>

# 9. On github.com, click "Compare & pull request".
#    CHANGE THE BASE DROPDOWN from main to Proximity_Detector, then submit.
#    Ask a teammate to review it.
```

Every PR has three parts: **the function**, **its tests green**, and **a
markdown file in `docs/proximity/`**. See
[docs/proximity/PR_GUIDE.md](../../../docs/proximity/PR_GUIDE.md) for how to
write the description and how to review someone else's.

Rules from the playbook: pure functions only (same input → same output, no
files, no network, no globals). If you can't tell the answer from the inputs,
return `None` / `False` / `[]` — abstain, never guess.

## Cards

### Erik — `tracks.py: interpolate_to_grid`
**Hardest card. The one the plan calls the #1 source of phantom detections.**
Given one aircraft's reports at random times, produce a report at every whole
second between the first and last. Linear blend for positions/altitude/speed,
short-way-round blend for the compass track, skip gaps > 30 s.
Tests: `test_proximity_tracks.py` (8). Helpers `_lerp` and `_lerp_angle` are
already written for you — use them.

### Manni — `geometry.py: to_local_xy, velocity_xy, time_to_cpa, predicted_separation`
**The actual math. Four short functions; each formula is in its docstring.**
Local flat-earth projection (don't forget the cos), speed+track → (vx, vy)
(sin for x, cos for y — compass, not maths), `t_cpa = -(r·v)/|v|²`, and
straight-line extrapolation to that time.
Tests: `test_proximity_geometry.py` (15). `haversine_nm` is done as a model.

### CalebG — `pairs.py: is_airborne, candidate_pairs`
**Filtering. No heavy math, but the logic has to be exactly right.**
`is_airborne` is a two-line rule from the config. `candidate_pairs` buckets
aircraft into grid cells with the provided `cell_of`, then pairs up aircraft in
the same or touching cells and drops pairs that fail the cheap checks.
Tests: `test_proximity_pairs.py` (13). Start with `is_airborne` — it's five
tests and twenty minutes.

### CalebK — `detector.py: severity_for, flag_pair`
**The rulebook. Read the tiers from the config, never type a number.**
`severity_for` walks `cfg.tiers` top to bottom and returns the first tier
where both the horizontal AND vertical limit hold. `flag_pair` applies the
gates (converging, within 120 s) and then calls `severity_for`.
Tests: `test_proximity_rules.py` (19, mostly one table). The boundary cases
matter: 0.5 nm is NOT inside a `< 0.5` tier.

### Paul — `detector.py: ProximityDetector.detect_observations`
Wire the four stages together. One Detection per PAIR, not per second — keep
the instant with the smallest predicted horizontal separation. The docstring
has the pseudo-code. Only goes green once everyone else's is in.
Tests: `test_proximity_detector.py` (9). Then `python scripts/run_proximity.py
air/fixtures/proximity_head_on.json` prints the real JSON. That's the Week 6 MVP.

### Caroline & Faith — `DESIGN_CARD.md`
No code. Fill in the one-page Detector Design Card (a required deliverable).
Every answer is in the project plan; the card just needs it condensed into
eight boxes. Template and hints are in the file. Review it with Paul, then
open a PR like everyone else — same branch/commit/push steps, just a `.md`
file instead of a `.py`.

## When you're stuck

1. Read the docstring again, slowly. The formula is there.
2. Read the failing test. It tells you the exact input and the exact expected
   output — work it by hand on paper.
3. Ask Paul. Not finishing in the hour is normal; ask before doing extra hours.

## What's already done (don't redo)

`config.py` + `configs/detectors/proximity.yaml` (all thresholds), `haversine_nm`,
`group_tracks`, `align_tracks`, `cell_of`, `pair_geometry`, `confidence_for`,
`explanation_facts`, `to_detection`, the five synthetic fixtures in
`air/fixtures/proximity_*.json` and the script that generates them
(`scripts/make_proximity_fixtures.py`).
