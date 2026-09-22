# Geometry

**Author:** Manni · **PR:** pending · **File:** `air/detectors/proximity/geometry.py`

## What it does

These four functions turn aircraft locations, ground speeds, and compass tracks into local position and velocity vectors. They then find when a pair will be closest and its horizontal and vertical separation at a chosen time. The detector uses these measurements to evaluate a pair's proximity.

## Inputs and outputs

| Function | Inputs | Output | Units |
|---|---|---|---|
| `to_local_xy` | Latitude, longitude, reference latitude and longitude | East and north offsets | Degrees in; metres out |
| `velocity_xy` | Ground speed and compass track | East and north velocities | Knots and degrees in; m/s out |
| `time_to_cpa` | Relative position and velocity | Signed time, or `None` for near-zero relative speed | Metres and m/s in; seconds out |
| `predicted_separation` | Relative position, velocity, time, altitude difference and climb-rate difference | Horizontal and absolute vertical gap | Metres, m/s, seconds, feet and ft/min in; nm and feet out |

## How it works

- The local projection takes latitude and longitude differences in radians, multiplies by Earth's radius, and scales longitude by `cos(reference latitude)`.
- Compass tracks start at north and increase clockwise, so east velocity uses `speed × sin(track)` and north velocity uses `speed × cos(track)` after converting knots to m/s.
- With relative position `r` and velocity `v`, closest approach occurs at `t = -(r · v) / |v|²`. Positive time is in the future; negative time is in the past.
- At a chosen time, horizontal separation is `|r + v × t| / 1852` nautical miles. Vertical separation is `|altitude difference + climb-rate difference × t / 60|` feet.

## Decisions and trade-offs

- A relative speed under `1e-9` m/s returns `None` for closest-approach time; dividing by a nearly zero speed would produce an unstable answer.
- Closest-approach time remains negative for diverging pairs. The caller decides whether a past encounter matters.
- The reference latitude determines the east-west scale for both positions in a pair.

## What it does NOT handle

The projection is meant for nearby aircraft, roughly within 50 nautical miles; it is not a route across large distances or the poles. Straight-line extrapolation assumes constant speed, heading, and climb rate, so turns and acceleration can change the actual closest approach. These functions do not select pairs, set alert thresholds, or assess intent.

## Tests

`tests/air/detectors/proximity/test_proximity_geometry.py` — 17 tests. They cover local east/north offsets, compass directions, approaching and diverging aircraft, stationary relative motion, and nonnegative separation after a vertical crossing.
