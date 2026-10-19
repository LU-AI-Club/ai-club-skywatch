# build_features

**What it does:** runs the whole calculation stage over every aircraft in a stream.
**File:** air/detectors/spoofing/features.py
**Inputs:** any iterable of `AdsbObservation`, and `max_gap_s`.
**Output:** a list of `SpoofingFeatureRecord`.
**How it's tested:** one record per consecutive pair; no record spans a gap (four points around a ten-minute hole give 2 records in 2 segments, not 3); every aircraft is covered; a single report produces nothing; on the `clean_track` fixture it produces 39 records all implying 450 kt.
**Gotchas:** `segment_id` counts from 0 *per aircraft*, so two records sharing an id are only in the same stretch if they also share an `icao24`.

## The order matters

Group, then split, then pair. Pairing before splitting would compute features
across gaps, which is the single largest source of fake findings in this kind
of detector.
