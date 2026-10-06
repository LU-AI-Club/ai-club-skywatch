"""Feature calculations for ADS-B spoofing detection."""

import math


EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
	"""Return the great-circle distance between two degree coordinates in metres."""
	p1, p2 = math.radians(lat1), math.radians(lat2)
	delta_lat = p2 - p1
	delta_lon = math.radians(lon2 - lon1)
	haversine = (
		math.sin(delta_lat / 2) ** 2
		+ math.cos(p1) * math.cos(p2) * math.sin(delta_lon / 2) ** 2
	)
	return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))
