# Scripts

Command-line runners live here. A runner loads observations, constructs the
detector(s), and prints the emitted detections as JSON — a no-database way to
see a detector work end to end. Keep runners **thin**: parse args, load input,
call `detector.detect_observations(...)`, print `Detection.to_dict()`. All real
logic belongs in `air/` (normalizers, windowing, detectors), never in a script.

## `replay_csv.py` — windowed CSV replay (the main one)

Streams a readsb/tar1090 ADS-B CSV (default `data/lynchburg_adsb.csv`) through
the shared normalizer, slices it into **epoch-anchored time windows**, feeds each
window to the selected detector(s), and prints each `Detection` as JSON. This is
the one-shot form of how detection runs on a live feed (the same windowing logic,
there triggered on a timer over a rolling "last N minutes" slice).

```bash
# all available detectors, 60s tumbling windows
python scripts/replay_csv.py

# one detector, quick smoke on the earliest 5000 observations
python scripts/replay_csv.py --detector example_altitude --limit 5000

# sliding windows (overlap + automatic dedup) for a stateful detector
python scripts/replay_csv.py --detector proximity --window 30 --step 10

# write results to a file, no summary
python scripts/replay_csv.py --out detections.jsonl --quiet
```

Flags: `--detector` (repeatable; default = all), `--window` / `--step` seconds
(step defaults to window = tumbling; `step < window` = sliding, dedup auto-on),
`--limit`, `--max-windows`, `--receiver-id`, `--format {jsonl,json}`, `--out`,
`--quiet`. A summary (observations normalized/skipped, windows, detections per
detector) prints to stderr.

### Making your detector appear in the replay

The runner's registry maps each detector name to an entry point. A detector that
isn't built yet is **skipped with a note**, not an error. To light yours up with
no change to `replay_csv.py`, expose, in your detector package `__init__.py`,
either:

- a zero-arg factory `def build_detector(): return MyDetector(load_my_config())`, or
- a `BaseDetector` subclass with a zero-arg-friendly `__init__` (like
  `ExampleAltitudeDetector`).

Either must offer `detect_observations(list[AdsbObservation]) -> list[Detection]`.

## Per-detector wrappers (optional)

If a team wants a dedicated `run_<detector>.py` (mirroring the platform's
`scripts/run_*_detector.py`), keep it a one-liner over the same pieces —
`iter_observations(...)` → `iter_windows(...)` → `detector.detect_observations(...)`
— rather than duplicating logic.
