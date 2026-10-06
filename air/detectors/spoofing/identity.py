import json
import math
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional, Sequence


EARTH_RADIUS_M = 6_371_000.0
 
# Fallbacks used only if the SpoofingConfig doesn't define the field.
DEFAULT_MAX_SPEED_MPS = 450.0          # ~Mach 1.3; faster than any airliner
DEFAULT_MIN_HOPS = 3                   # impossible, direction-flipping hops in a row
DEFAULT_REVERSAL_TOLERANCE_DEG = 45.0  # how close to a 180-degree turn counts as a flip
DEFAULT_MIN_HOP_DISTANCE_M = 1.0       # ignore jitter when timestamps coincide

DEFAULT_CONFIG = {
    "window_s": 30,            # only compare reports this close in time
    "max_speed_kt": 900.0,     # fastest plausible speed for the aircraft
    "position_tolerance_km": 0.5,  # slack for GPS/decoding noise
}

KT_TO_KM_S = 1.852 / 3600

def _get(rec: Any, name: str) -> Any:
    return rec[name] if isinstance(rec, dict) else getattr(rec, name)
 
 
def _ts(rec: Any) -> float:
    t = _get(rec, "timestamp")
    return t.timestamp() if isinstance(t, datetime) else float(t)
 
 
def _cfg(config: Any, name: str, default: float) -> float:
    value = getattr(config, name, None)
    return default if value is None else value
 
 
def _hop(a: Any, b: Any) -> tuple[float, float, float, float]:
    """Return (dist_m, dt_s, east_m, north_m) for the move a -> b."""
    lat1, lon1 = math.radians(_get(a, "lat")), math.radians(_get(a, "lon"))
    lat2, lon2 = math.radians(_get(b, "lat")), math.radians(_get(b, "lon"))
    dlat, dlon = lat2 - lat1, lon2 - lon1
 
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    dist = 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))
 
    # Local flat-earth displacement vector, good enough for direction comparison.
    east = dlon * math.cos((lat1 + lat2) / 2) * EARTH_RADIUS_M
    north = dlat * EARTH_RADIUS_M
    return dist, _ts(b) - _ts(a), east, north
 


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


def flag_pingpong(records: Sequence[Any], config: Any) -> Optional[str]:
    """Flag A -> B -> A -> B style bouncing caused by two transmitters sharing an id.
 
    Fires when there are at least `pingpong_min_hops` (default 3) consecutive
    impossible hops, each reversing direction relative to the previous one.
    A single faked position yields only two such hops (out and back), so it
    does not fire.
 
    `records` must all belong to one aircraft; they are sorted by timestamp.
    Returns a reason string, or None.
    """
    min_hops = int(_cfg(config, "pingpong_min_hops", DEFAULT_MIN_HOPS))
    max_speed = _cfg(config, "max_speed_mps", DEFAULT_MAX_SPEED_MPS)
    tol_deg = _cfg(config, "pingpong_reversal_tolerance_deg", DEFAULT_REVERSAL_TOLERANCE_DEG)
    min_dist = _cfg(config, "pingpong_min_hop_distance_m", DEFAULT_MIN_HOP_DISTANCE_M)
    cos_limit = -math.cos(math.radians(tol_deg))  # cos(angle) <= this means "reversed"
 
    if len(records) < min_hops + 1:
        return None
 
    ordered = sorted(records, key=_ts)
 
    run = 0                              # current streak of impossible, flipping hops
    prev_vec: Optional[tuple[float, float]] = None
    run_dists: list[float] = []
    run_speeds: list[float] = []
 
    for a, b in zip(ordered, ordered[1:]):
        dist, dt, east, north = _hop(a, b)
 
        if dt <= 0:
            impossible = dist > min_dist   # two places at the same instant
            speed = math.inf if impossible else 0.0
        else:
            speed = dist / dt
            impossible = speed > max_speed
 
        if not impossible:
            run, prev_vec = 0, None        # a plausible hop breaks the pattern
            run_dists.clear(); run_speeds.clear()
            continue
 
        vec = (east, north)
        flipped = False
        if prev_vec is not None:
            norm = math.hypot(*prev_vec) * math.hypot(*vec)
            flipped = norm > 0 and (prev_vec[0] * vec[0] + prev_vec[1] * vec[1]) / norm <= cos_limit
 
        if flipped:
            run += 1
        else:
            # Impossible but not a reversal: start a fresh streak with this hop.
            run = 1
            run_dists.clear(); run_speeds.clear()
        run_dists.append(dist)
        run_speeds.append(speed)
        prev_vec = vec
 
        if run >= min_hops:
            finite = [s for s in run_speeds if math.isfinite(s)]
            peak = f"{max(finite):.0f} m/s" if finite else "simultaneous"
            return (
                f"pingpong: {run} consecutive impossible hops reversing direction "
                f"(~{sum(run_dists) / len(run_dists) / 1000:.1f} km apart, "
                f"peak implied speed {peak}, limit {max_speed:.0f} m/s)"
            )
 
    return None
 
