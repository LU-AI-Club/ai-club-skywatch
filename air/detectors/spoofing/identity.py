import json
import math
from collections import defaultdict
from datetime import datetime

DEFAULT_CONFIG = {
    "window_s": 30,            # only compare reports this close in time
    "max_speed_kt": 900.0,     # fastest plausible speed for the aircraft
    "position_tolerance_km": 0.5,  # slack for GPS/decoding noise
}

KT_TO_KM_S = 1.852 / 3600


def _parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def _distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km (haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def flag_coexistence(reports, config=None):
    """
    Flag an ICAO address reported from two places at once.

    reports: list of dicts with icao24, observed_at, latitude, longitude
             (receiver_id is used in the message if present)
    config:  optional dict overriding DEFAULT_CONFIG

    Returns a reason string if a conflict is found, else None.
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}

    by_id = defaultdict(list)
    for r in reports:
        by_id[r["icao24"]].append((_parse_time(r["observed_at"]), r))

    for icao, items in by_id.items():
        items.sort(key=lambda x: x[0])
        for i, (t1, a) in enumerate(items):
            for t2, b in items[i + 1:]:
                dt = t2 - t1
                if dt > cfg["window_s"]:
                    break  # sorted, so everything after is even later
                dist = _distance_km(a["latitude"], a["longitude"],
                                    b["latitude"], b["longitude"])
                max_dist = (cfg["max_speed_kt"] * KT_TO_KM_S * dt
                            + cfg["position_tolerance_km"])
                if dist > max_dist:
                    return (
                        f"{icao} reported {dist:.1f} km apart in {dt:.0f}s "
                        f"(max plausible {max_dist:.1f} km); "
                        f"receivers {a.get('receiver_id')} / {b.get('receiver_id')}"
                    )
    return None
