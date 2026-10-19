# flag_subterrain

**What it does:** flags an aircraft reporting a position below the ground beneath it.
**File:** air/detectors/spoofing/physics.py
**Inputs:** a `SpoofingFeatureRecord`, the terrain elevation in feet (or None), and a `SpoofingConfig`.
**Output:** a reason string when it fires, otherwise None.
**How it's tested:** an aircraft below the ground fires; one above it does not; missing elevation data abstains; `subterrain_depth_ft` reports depth as a positive number and None when the aircraft is above ground.
**Gotchas:** abstains when no elevation is available rather than assuming sea level. Assuming would flag every approach to a high-altitude airport.

## Depth is positive

Events store `measured` as a positive value, so `subterrain_depth_ft` reports
depth rather than a negative height: 300.0 means 300 ft underground. The
threshold is 0 and the unit is `ft`.

## Needs data we do not have yet

Elevation comes from SRTM or USGS, both free. The full download belongs in
`data/raw/`, which git ignores; commit only a small sample.
