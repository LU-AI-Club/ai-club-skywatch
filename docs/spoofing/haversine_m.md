# `haversine_m`

`haversine_m(lat1, lon1, lat2, lon2)` returns the great-circle distance between
two latitude/longitude coordinates, in metres. Coordinates must be supplied in
decimal degrees, in latitude-then-longitude order.

The function models Earth as a sphere with radius 6,371,000 metres. Given
latitudes and longitudes converted to radians, it computes:

```text
a = sin²((lat2 - lat1) / 2)
	+ cos(lat1) * cos(lat2) * sin²((lon2 - lon1) / 2)
distance = 2 * 6,371,000 * asin(sqrt(a))
```

This is a surface distance: altitude is not considered. The function assumes
valid geographic coordinates and does not perform range validation.

## Example

```python
from air.detectors.spoofing.features import haversine_m

distance_m = haversine_m(37.4138, -79.1422, 37.42116, -79.132932)
```

These coordinates are the first two reports in
`air/fixtures/spoofing/clean_track.json`; their distance is approximately
1,157.5 metres. The corresponding pytest check is in
`tests/air/detectors/spoofing/test_spoofing_features.py`.
