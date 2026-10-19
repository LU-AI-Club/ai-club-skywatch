# Spoofing Team Work Sheet

This is the working copy. The PDF handout is a snapshot of it — if the two
disagree, this file wins.

## 1. Get the code

You need VS Code, Python 3.12, git, and your GitHub account added to
`LU-AI-Club`. Message Will if you're missing any.

Open a terminal and run these one at a time. **Windows:**

```bash
git clone https://github.com/LU-AI-Club/ai-club-skywatch.git
cd ai-club-skywatch
git checkout Spoofing
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install ".[dev]"
pytest -q
```

On Mac, line 5 is `source .venv/bin/activate` instead.

If the last line prints dots and `passed`, you're set up.

**Two things to note.** The branch is `Spoofing` with a capital S, and we never
work on `main`. And `(.venv)` has to show at the start of your terminal line, or
`pytest` won't be found. Every new terminal window needs the activate line again.

To make your own branch for a task:

```bash
git checkout -b spoofing/<your-thing>
```

## 2. Where the test data lives

[`air/fixtures/spoofing/`](../../air/fixtures/spoofing) — 17 small JSON files of
made-up flights. We planted the problems ourselves, so we know the right answer
for each one. Open any of them in VS Code and read it.

[`air/fixtures/spoofing/README.md`](../../air/fixtures/spoofing/README.md)
describes what is in each file. **Read that first.**

To load a fixture in a test, use the helper that's already in the repo:

```python
def test_teleport_fires(observations_from):
    obs = observations_from("spoofing/pos_teleport.json")
```

That hands back a list of `AdsbObservation` objects.

## 3. Your functions

All paths are from the repo root. Write one function per pull request, not all
of them at once.

The two records everyone passes around already exist:

```python
from air.detectors.spoofing.records import SpoofingFeatureRecord, SpoofingEvent
```

### Will — `air/normalizers/lynchburg_csv.py` and `air/detectors/spoofing/detector.py`

| Function | Description | In | Out |
|---|---|---|---|
| `rc_to_nic` | Convert the file's accuracy-in-metres value into a 0–11 GPS-trust score | metres | int 0–11 or `None` |
| `is_direct_adsb` | Keep only directly received messages, not relayed ones | one CSV row | bool |
| `row_to_observation` | Turn one raw row into a clean record | one CSV row | `AdsbObservation` or `None` |
| `load_csv` | Same for the whole file | file path | list of `AdsbObservation` |
| `get_required_data` | Declare what data the detector needs | none | `DataRequirements` |
| `detect_observations` | Run every stage in order | list of `AdsbObservation` | list of `Detection` |
| `detect` | Same, in the form the platform calls | `DetectionContext` | list of `Detection` |

**Test against:** `data/lynchburg_adsb.csv`, the real file.

### Christopher — `air/detectors/spoofing/features.py`

| Function | Description | In | Out |
|---|---|---|---|
| `haversine_m` | Distance between two points on Earth | `lat1, lon1, lat2, lon2` in degrees | metres |
| `heading_delta_deg` | Turn between two headings, handling 359° → 1° | two headings | −180 to 180 |
| `group_by_aircraft` | Sort messages into one list per plane, by time | list of `AdsbObservation` | dict of id → list |
| `split_segments` | Break a plane's track wherever it went quiet too long | one plane's list, `max_gap_s` | list of lists |
| `build_pair_features` | Time, distance, implied speed, climb and turn for two messages | two `AdsbObservation` | `SpoofingFeatureRecord` or `None` |
| `build_features` | Run that across every pair, for every plane | list of `AdsbObservation` | list of `SpoofingFeatureRecord` |

**Test against:** `clean_track.json` for the maths, `neg_benign_gap.json` for
`split_segments`.

### Henry — `air/detectors/spoofing/config.py` and `air/detectors/spoofing/physics.py`

| Function | Description | In | Out |
|---|---|---|---|
| `SpoofingConfig` | Every limit in one place: 1000 kt, 10°/s, 50 kt, 2000 fpm, 60 s | — | dataclass |
| `to_parameters` | Those limits as a dict, to record on each alert | a config | dict |
| `flag_teleport` | Moving faster than 1000 knots | feature record, config | reason string or `None` |
| `flag_turn_rate` | Turning faster than 10° per second | feature record, config | reason or `None` |
| `flag_speed_delta` | Claimed and calculated speed disagree by over 50 kt or 30% | feature record, config | reason or `None` |
| `flag_vrate_delta` | Claimed and calculated climb rate disagree by over 2000 fpm | feature record, config | reason or `None` |
| `flag_nic_floor` | GPS-trust stuck at 0 or 1 for a sustained stretch | one segment, config | reason or `None` |

**Test against:** one positive and one negative per rule — `pos_teleport.json`
and `neg_tailwind_cruise.json`; `pos_impossible_turn.json` and
`neg_standard_turn.json`; `pos_speed_contradiction.json` and
`clean_track.json`; `pos_vrate_contradiction.json` and
`neg_legal_descent.json`; `pos_integrity_collapse.json` and
`neg_brief_nic_dip.json`.

### Ryan — `air/detectors/spoofing/reference.py` and `air/detectors/spoofing/identity.py`

| Function | Description | In | Out |
|---|---|---|---|
| `load_icao_blocks` | Load the table of which id ranges belong to which country | file path | list of (start, end, country) |
| `load_faa_registry` | Load the FAA aircraft list | file path | dict of id → record |
| `flag_coexistence` | One id reporting from two places at once | tracks, config | reason or `None` |
| `flag_pingpong` | An id bouncing between two places, meaning two transmitters | feature records, config | reason or `None` |
| `flag_reappearance` | Came back after silence somewhere it couldn't have reached | two observations, config | reason or `None` |
| `flag_registry_mismatch` | The registry disagrees with how the plane is flying | observation, registry, blocks | reason or `None` |
| `flag_identity_drift` | One id showing two callsigns | one plane's track | reason or `None` |

**Test against:** `icao_blocks_sample.csv` and `faa_registry_sample.csv` for the
loaders; `pos_impersonation.json` and `neg_close_formation.json` for coexistence
and ping-pong; `pos_gap_takeover.json` and `neg_benign_gap.json` for
reappearance; `pos_registry_mismatch.json` for the registry check.

### Ian — `air/detectors/spoofing/reference.py` (Ryan's file, different functions)

| Function | Description | In | Out |
|---|---|---|---|
| `country_for_icao24` | Which country owns this id | id, block list | country or `None` |
| `lookup_registration` | Which aircraft this id is registered to | id, registry | record or `None` |

**Test against:** `icao_blocks_sample.csv` and `faa_registry_sample.csv`, or
values you type into the test yourself.

Then join Ryan on `identity.py`. Agree who takes which flag first.

### Daniel — `air/detectors/spoofing/scoring.py` and `air/detectors/spoofing/emit.py`

| Function | Description | In | Out |
|---|---|---|---|
| `to_detection` | Build the final alert. **Start as a stub with fixed values** | `SpoofingEvent`, config | `Detection` |
| `anomaly_score` | How far past the limit, 0.5 at the line up to 1.0 | measured, threshold, margin | float 0–1 |
| `confidence_for` | How sure we are the data was good enough to judge | event | float 0–1 |
| `severity_for` | HIGH, MEDIUM or LOW depending which rule fired | gate name | `SeverityLevel` |
| `should_abstain` | Whether to stay quiet instead of alerting | score, confidence, config | bool |
| `explanation_facts` | Plain sentences stating what we saw. Facts only, no conclusions | event | list of strings |
| `build_evidence` | Attach the messages that prove it | event | list of `Evidence` |
| `build_provenance` | Record the data source and settings used | event, config | `ProvenanceRecord` |

**Test against:** nothing at first — the stub returns fixed values. Later, events
you build by hand in the test.

Copy `to_detection` from
[`air/detectors/_example_altitude/detector.py`](../../air/detectors/_example_altitude/detector.py).
Import `Detection` from `contracts`, never rewrite it, and never edit anything in
`contracts/`.

### Noah — `scripts/evaluate_spoofing.py`

| Function | Description | In | Out |
|---|---|---|---|
| `run_on_fixtures` | Run the detector over every fixture | detector, fixture folder | list of results |
| `confusion_counts` | Count catches, false alarms and misses per rule | results | dict of counts |
| `precision_recall` | Of what we flagged, how much was right; of what we planted, how much we caught | counts | (precision, recall) |
| `sweep_threshold` | Try one limit at many values | setting, values, fixtures | table of results |
| `implied_speed_histogram` | Chart showing where the teleport limit belongs | feature records | chart |

**Test against:** every file in `air/fixtures/spoofing/`. The `pos_` files should
produce an alert and the `neg_` and `clean_` files should not.

### Silas — `scripts/evaluate_spoofing.py` (Noah's file, different functions)

| Function | Description | In | Out |
|---|---|---|---|
| `alerts_per_hour` | How many alerts a real person would get | detections, hours | float |
| `attribute_false_positives` | Group false alarms by cause | false positives | counts by cause |

**Test against:** the same folder, or values you type into the test yourself —
your functions just count and group lists, so a short made-up list is enough.

### Using AI to write it

Use an AI that can read the repo, such as the Codex extension in VS Code (free
with a ChatGPT account) or Claude Code. Open the repo folder first, then point it
at our files so it matches our field names instead of inventing its own.

For example:

```markdown
Read air/detectors/spoofing/records.py and
air/detectors/_example_altitude/detector.py first.

Now write flag_teleport in air/detectors/spoofing/physics.py. It takes a
SpoofingFeatureRecord and a SpoofingConfig, and returns "TELEPORT" if
implied_speed_kt is over cfg.teleport_kt, otherwise None. Match the style
of flag_altitude. Also write a pytest test with one case that fires and
one that doesn't.
```

Daniel: have it read `contracts/detection.py` as well.

If you're using a chat window that can't see the repo, paste those files in
yourself first.

**The code only counts once `pytest -q` passes.** That is what catches AI code
that looks right and isn't.

## 4. How to test your work

A test is a small Python file that checks your function gives the right answer.
Put yours in `tests/air/detectors/spoofing/`, named `test_spoofing_<thing>.py`.

Run everything from the repo root:

```bash
pytest -q
```

Dots mean passing. Red means something broke, and the output names which check
failed and what it got instead.

Every test needs **one case that should fire and one that should not.** A rule
that flags everything passes a one-sided test and is useless.

Example, using values typed straight into the test:

```python
from types import SimpleNamespace
from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.physics import flag_teleport

def test_teleport_fires():
    record = SimpleNamespace(implied_speed_kt=21285.0)
    assert flag_teleport(record, SpoofingConfig()) == "TELEPORT"

def test_tailwind_does_not_fire():
    record = SimpleNamespace(implied_speed_kt=780.0)
    assert flag_teleport(record, SpoofingConfig()) is None
```

Example using a fixture file instead:

```python
def test_clean_track_is_quiet(observations_from):
    obs = observations_from("spoofing/clean_track.json")
    assert len(obs) == 40
```

To run just your own file:

```bash
pytest tests/air/detectors/spoofing/test_spoofing_physics.py -v
```

## 5. Finishing a function

A function is done when all five of these are true:

- [ ] The function is written, in the file listed under your name and nowhere else.
- [ ] A test covers it, with one case that fires and one that doesn't.
- [ ] `pytest -q` passes on your machine.
- [ ] A short note exists at `docs/spoofing/<function_name>.md`.
- [ ] A pull request is open into `Spoofing`, and Will approved it.

### The note

```markdown
# <function_name>

**What it does:** one sentence.
**File:** path/to/file.py
**Inputs:** name, type, units
**Output:** type, units
**How it's tested:** the cases in your test, in plain words
**Gotchas:** anything it doesn't handle
```

### Opening the pull request

```bash
git add .
git commit -m "Add haversine_m"
git push -u origin spoofing/<your-branch>
```

Then open the PR on GitHub, set the target to **`Spoofing`** (not `main`), and
say what you added, why, how you tested it, and what Will should look at.

### Rules

- One function per pull request. Not five.
- Never work on `main`.
- Never edit anything in `contracts/`.
- If a value you need is missing, return `None`. Don't guess.
- Using AI is fine, but you have to understand every line and be able to explain it.
- Stuck for 30 minutes? Message Will.
