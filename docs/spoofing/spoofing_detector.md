# SpoofingDetector

**What it does:** the class that runs every stage of the detector in order.
The integration point - the only file that knows what order the lanes run in.
**File:** air/detectors/spoofing/detector.py
**Inputs:** none to construct.
**Output:** the detector object the platform runs.
**How it's tested:** the four class attributes match what the platform expects,
and `BaseDetector` validates them on construction.
**Gotchas:** `implementation_type` is `RULE_BASED` and must stay that way.
TCE/CAATS reads it to decide which governance gates apply, and claiming machine
learning would invite the wrong ones.

## The four attributes

| Attribute | Value |
|---|---|
| detector_id | `skywatch.spoofing` |
| detector_version | `0.1.0` |
| domain | `air` |
| implementation_type | `RULE_BASED` |

Shape copied from `ExampleAltitudeDetector` in
`air/detectors/_example_altitude/detector.py`.
