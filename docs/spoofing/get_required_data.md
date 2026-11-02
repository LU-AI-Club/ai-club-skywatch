# get_required_data

**What it does:** tells the platform what data the detector needs before it can
run.
**File:** air/detectors/spoofing/detector.py
**Inputs:** none - a method on `SpoofingDetector`.
**Output:** a `DataRequirements` object.
**How it's tested:** the returned object names the `adsb_position` observation
type, the `adsb` source, the `observations` auxiliary key, and a one-hour
lookback.
**Gotchas:** `lookback_hours` is the one judgement call here.

| Field | Value |
|---|---|
| observation_types | `("adsb_position",)` |
| source_names | `("adsb",)` |
| auxiliary_data_keys | `("observations",)` |
| lookback_hours | `1.0` |

## Why one hour of lookback

Every check in this detector compares an observation against earlier ones from
the same aircraft. A single report carries nothing to contradict, so it can
never be judged alone. The platform therefore has to hand us history, and one
hour comfortably covers a track long enough to establish normal behaviour.
