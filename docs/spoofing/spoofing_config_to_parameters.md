# SpoofingConfig.to_parameters

**What it does:** flattens every setting into a dict, recorded on each Detection.
**File:** air/detectors/spoofing/config.py
**Inputs:** none - a method on `SpoofingConfig`.
**Output:** a dict of every field and its value.
**How it's tested:** it carries every setting; an overridden value appears rather than the default.
**Gotchas:** there are two `to_parameters` in this project. This one is on `SpoofingConfig`. The other is on `SpoofingEvent` in `records.py`. Same name, different object, different file.

## Why it exists

An alert is only interpretable next to the limits that produced it. Change a
threshold next week and yesterday's detections must still say what they were
measured against - otherwise nobody can tell whether 1,100 kt was over the
line at the time.
