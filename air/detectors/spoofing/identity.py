from __future__ import annotations
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
DEFAULT_REAPPEARANCE_MARGIN_M = 0.0  # extra slack added to the reachable radius
# Ground speed is airspeed plus whatever the wind is doing, and a jet stream
# adds 200-300 kt routinely, so a small flat margin flags honest traffic:
# `neg_tailwind_cruise` is a real Gulfstream 292 kt over its book speed.
#
# A flat margin alone cannot separate the two cases. What does is the ratio:
#
#   Gulfstream  780 / 488 = 1.6x   a tailwind
#   Cessna 172  450 / 124 = 3.6x   not that aircraft
#
# So the speed check fires on either a very large absolute excess or a
# proportional one. Wind adds an absolute amount, never a multiple.
DEFAULT_REGISTRY_SPEED_MARGIN_KT = 350.0
DEFAULT_REGISTRY_SPEED_RATIO = 2.0
DEFAULT_REGISTRY_CEILING_MARGIN_FT = 1000.0  # altitude reporting noise

DEFAULT_CONFIG = {
    "window_s": 30,            # only compare reports this close in time
    "max_speed_kt": 900.0,     # fastest plausible speed for the aircraft
    "position_tolerance_km": 0.5,  # slack for GPS/decoding noise
}

KT_TO_KM_S = 1.852 / 3600

def _get(rec: Any, *names: str) -> Any:
    """Read the first field a record actually has, from several spellings.

    These rules are fed two shapes. Tests and fixtures hand in plain dicts
    using the raw feed's names (``lat``, ``lon``, ``timestamp``); the
    pipeline hands in ``AdsbObservation`` objects, whose contract names are
    ``latitude``, ``longitude`` and ``observed_at``. Rather than force either
    side to convert, the accessor accepts both.
    """
    for name in names:
        if isinstance(rec, dict):
            if name in rec:
                return rec[name]
        elif hasattr(rec, name):
            return getattr(rec, name)
    raise KeyError(f"record has none of {names!r}")


def _lat(rec: Any) -> float:
    return float(_get(rec, "latitude", "lat"))


def _lon(rec: Any) -> float:
    return float(_get(rec, "longitude", "lon"))


def _ts(rec: Any) -> float:
    """Seconds since the epoch, from a datetime, an ISO string or a number."""
    t = _get(rec, "observed_at", "timestamp")
    if isinstance(t, datetime):
        return t.timestamp()
    if isinstance(t, str):
        return _parse_time(t)
    return float(t)

 
def _cfg(config: Any, name: str, default: float) -> float:
    value = getattr(config, name, None)
    return default if value is None else value
 
 
def _hop(a: Any, b: Any) -> tuple[float, float, float, float]:
    """Return (dist_m, dt_s, east_m, north_m) for the move a -> b."""
    lat1, lon1 = math.radians(_lat(a)), math.radians(_lon(a))
    lat2, lon2 = math.radians(_lat(b)), math.radians(_lon(b))
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


def _receiver(rec: Any) -> Any:
    """The receiver that heard a report, when the shape carries one."""
    try:
        return _get(rec, "receiver_id")
    except KeyError:
        return None


def flag_coexistence(reports, config=None):
    """
    Flag an ICAO address reported from two places at once.

    reports: any mix of dicts or ``AdsbObservation`` objects. Dicts may use
             either the feed's names (``lat``, ``lon``, ``timestamp``) or the
             contract's (``latitude``, ``longitude``, ``observed_at``).
    config:  a dict overriding DEFAULT_CONFIG, or a ``SpoofingConfig``.

    One aircraft cannot be in two places at once. For every pair of reports
    carrying the same id within ``window_s`` of each other, the distance
    between them is compared against what a single aircraft could have
    covered in that time. Farther apart than that means two transmitters are
    using one identity.

    Returns a reason string if a conflict is found, else None.
    """
    if config is None:
        cfg = dict(DEFAULT_CONFIG)
    elif isinstance(config, dict):
        cfg = {**DEFAULT_CONFIG, **config}
    else:
        # A SpoofingConfig: teleport_kt is the fastest plausible ground speed.
        cfg = {
            **DEFAULT_CONFIG,
            "max_speed_kt": getattr(config, "teleport_kt", DEFAULT_CONFIG["max_speed_kt"]),
        }

    by_id = defaultdict(list)
    for r in reports:
        by_id[_get(r, "icao24")].append((_ts(r), r))

    for icao, items in by_id.items():
        items.sort(key=lambda x: x[0])
        for i, (t1, a) in enumerate(items):
            for t2, b in items[i + 1:]:
                dt = t2 - t1
                if dt > cfg["window_s"]:
                    break  # sorted, so everything after is even later
                dist = _distance_km(_lat(a), _lon(a), _lat(b), _lon(b))
                max_dist = (cfg["max_speed_kt"] * KT_TO_KM_S * dt
                            + cfg["position_tolerance_km"])
                if dist > max_dist:
                    return (
                        f"{icao} reported {dist:.1f} km apart in {dt:.0f}s "
                        f"(max plausible {max_dist:.1f} km); "
                        f"receivers {_receiver(a)} / {_receiver(b)}"
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
 
 
def flag_reappearance(last_before: Any, first_after: Any, config: Any) -> Optional[str]:
    """Flag an aircraft that reappears somewhere it could not have reached.
 
    Draws a circle around the last known position with
    radius = max_speed_mps * gap_seconds (+ optional margin). A reappearance
    inside (or exactly on) the circle is normal. Outside means something else
    picked up the id while the real aircraft was out of range.
 
    The caller decides what counts as a gap; this function judges any pair
    it is given. A gap of zero or less is not a gap, so it returns None.
    """
    max_speed = _cfg(config, "max_speed_mps", DEFAULT_MAX_SPEED_MPS)
    margin = _cfg(config, "reappearance_margin_m", DEFAULT_REAPPEARANCE_MARGIN_M)
 
    dist, gap, _, _ = _hop(last_before, first_after)
    if gap <= 0:
        return None
 
    radius = max_speed * gap + margin
    if dist <= radius:
        return None
 
    return (
        f"reappearance: returned {dist / 1000:.1f} km from last position after a "
        f"{gap:.0f} s gap; at most {radius / 1000:.1f} km reachable at {max_speed:.0f} m/s"
    )


def flag_registry_mismatch(observation: Any, registry: Any, blocks: Any,
                           config: Any = None) -> Optional[str]:
    """Flag an aircraft flying beyond what its registered type can do.

    Looks the id up in the FAA registry and compares the observed
    ``ground_speed_kt`` and ``altitude_ft`` against the record's
    ``max_speed_kt`` and ``ceiling_ft`` (plus margins for wind and altitude
    noise). A Cessna 172 at 450 kt and 35,000 ft means the id is borrowed.

    Does not fire when:
      - the id isn't in the registry (foreign aircraft; the FAA only covers US)
      - the callsign differs from the tail number (airlines fly under their
        own callsign), so the callsign is never compared at all
      - speed or altitude is missing; that check abstains

    ``blocks`` is only used to name the allocating country in the reason.
    Returns a reason string, or None.
    """
    from air.detectors.spoofing.reference import country_for_icao24, lookup_registration

    def field(name: str) -> Any:
        if isinstance(observation, dict):
            return observation.get(name)
        return getattr(observation, name, None)

    icao24 = field("icao24")
    record = lookup_registration(icao24, registry)
    if record is None:
        return None

    speed_margin = _cfg(config, "registry_speed_margin_kt", DEFAULT_REGISTRY_SPEED_MARGIN_KT)
    ceiling_margin = _cfg(config, "registry_ceiling_margin_ft", DEFAULT_REGISTRY_CEILING_MARGIN_FT)

    speed_ratio = _cfg(config, "registry_speed_ratio", DEFAULT_REGISTRY_SPEED_RATIO)

    problems = []
    speed = field("ground_speed_kt")
    # A max speed of 0 means the registry has no figure for this record --
    # ground vehicles carry one, and anything moving beats a ratio against
    # zero. Without this guard `neg_ground_vehicle` flags at 12 kt.
    if speed is not None and record.max_speed_kt and record.max_speed_kt > 0:
        if (
            speed > record.max_speed_kt + speed_margin
            or speed > record.max_speed_kt * speed_ratio
        ):
            problems.append(f"{speed:.0f} kt vs max {record.max_speed_kt} kt")
    altitude = field("altitude_ft")
    if altitude is not None and altitude > record.ceiling_ft + ceiling_margin:
        problems.append(f"{altitude:.0f} ft vs ceiling {record.ceiling_ft} ft")

    if not problems:
        return None

    country = country_for_icao24(icao24, blocks) or "unallocated block"
    return (
        f"registry_mismatch: {icao24} is registered as {record.n_number} "
        f"({record.manufacturer} {record.model}, {country}) but observed "
        + "; ".join(problems)
    )


def flag_identity_drift(observations: Sequence[Any]) -> Optional[str]:
    """Flag one id broadcasting two different callsigns in the same session.

    ``observations`` must all belong to one aircraft. They are walked in time
    order (``observed_at`` or ``timestamp`` if present, otherwise as given).
    Callsigns are compared after trimming spaces and uppercasing, since
    ADS-B pads them to 8 characters. Blank or missing callsigns are skipped,
    not counted as a change.

    Returns a reason string naming the first change, or None.
    """
    def field(obs: Any, name: str) -> Any:
        if isinstance(obs, dict):
            return obs.get(name)
        return getattr(obs, name, None)

    def when(obs: Any) -> Any:
        t = field(obs, "observed_at")
        if t is None:
            t = field(obs, "timestamp")
        if isinstance(t, str):
            return _parse_time(t)
        if isinstance(t, datetime):
            return t.timestamp()
        return t

    times = [when(o) for o in observations]
    if all(t is not None for t in times):
        ordered = [o for _, o in sorted(zip(times, observations), key=lambda p: p[0])]
    else:
        ordered = list(observations)

    first: Optional[str] = None
    for obs in ordered:
        raw = field(obs, "callsign")
        callsign = str(raw).strip().upper() if raw is not None else ""
        if not callsign:
            continue
        if first is None:
            first = callsign
        elif callsign != first:
            seen = []
            for o in ordered:
                c = str(field(o, "callsign") or "").strip().upper()
                if c and c not in seen:
                    seen.append(c)
            stamp = field(obs, "observed_at") or field(obs, "timestamp")
            at = f" at {stamp}" if stamp is not None else ""
            return (
                f"identity_drift: {field(obs, 'icao24') or 'aircraft'} changed callsign "
                f"{first} -> {callsign}{at} (callsigns seen: {', '.join(seen)})"
            )
    return None
 