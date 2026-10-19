# detect

**What it does:** the entry point the SENTINEL platform calls.
**File:** air/detectors/spoofing/detector.py
**Inputs:** a `DetectionContext`.
**Output:** a list of `Detection`.
**How it's tested:** a context carrying observations is passed through to
`detect_observations`; an empty context returns an empty list rather than
raising.
**Gotchas:** observations arrive in `context.auxiliary_data["observations"]`,
**not** in `context.observations`.

## Why auxiliary_data

`DetectionContext.observations` is typed as a sequence of plain mappings and
validates that on construction, so it will not carry `AdsbObservation`
dataclasses. Putting them in `auxiliary_data` is how the reference detector
solves the same problem - see the comment on `detect` in
`air/detectors/_example_altitude/detector.py`.

That is the only reason this method exists: it unpacks the context and hands
the list to `detect_observations`, which does the real work and is far easier
to call from a test.
