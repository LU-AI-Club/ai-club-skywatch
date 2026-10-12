# to_parameters

**What it does:** flattens a `SpoofingEvent` into a plain dictionary for
Detection metadata.
**File:** air/detectors/spoofing/records.py
**Inputs:** none - a method on `SpoofingEvent`.
**Output:** a dict of every field except `features`.
**How it's tested:** the gate, measured value, threshold and unit all survive
the flattening; `features` is left out; every other field is present.
**Gotchas:** there are two `to_parameters` in this project. This one is on
`SpoofingEvent`. Henry owns a separate one on `SpoofingConfig` in `config.py`
that flattens the thresholds. Same name, different object, different file.

## Why features is excluded

`features` holds whole `SpoofingFeatureRecord` objects. Detection metadata
wants flat, serialisable values, and the records are already attached to the
alert through `build_evidence`. Including them here would duplicate the
evidence and break serialisation.

## Why it exists

Every alert records the exact numbers that produced it. Without that, a
detection from last week is unreadable once someone changes a threshold - you
cannot tell whether 1,100 knots was over the limit at the time.
