# Scripts

Command-line runners live here, one per detector, mirroring the platform's
`scripts/run_*_detector.py`. A runner loads observations (from a fixture file
now, from the live normalizer later), constructs the detector, and prints the
emitted detections as JSON — a no-database way to see a detector work end to
end.

Add `run_<detector>.py` when your detector emits its first `Detection`
(syllabus Week 6). Keep them thin: parse args, load input, call
`detector.detect_observations(...)`, print `Detection.to_dict()`.
