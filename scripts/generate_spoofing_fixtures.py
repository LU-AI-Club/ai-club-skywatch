"""Generate the spoofing detector's test fixtures.

Writes JSON files into ``air/fixtures/spoofing/``. Each file is a list of
observation dicts matching :class:`air.models.observation.AdsbObservation`,
plus annotation keys beginning with ``_`` (``_label``, ``_note``) that
``AdsbObservation.from_dict`` ignores.

Everything here is deterministic: no randomness, no network, no clock reads.
Re-running it produces byte-identical files, so tests never change under you.

Usage (from the repo root)::

    python scripts/generate_spoofing_fixtures.py

Positive fixtures are named ``pos_*.json`` and must produce a detection.
Negative fixtures are named ``neg_*.json`` and must produce none.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OUT_DIR = Path(__file__).resolve().parents[1] / "air" / "fixtures" / "spoofing"

EARTH_RADIUS_M = 6_371_000.0
KT_TO_MS = 0.514444
M_TO_NM = 1.0 / 1852.0

# Near Lynchburg, VA — the centre of the real dataset.
LYH_LAT, LYH_LON = 37.4138, -79.1422

BASE_TIME = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# geometry helpers
# --------------------------------------------------------------------------
def destination(lat: float, lon: float, bearing_deg: float, distance_m: float):
    """Point reached from (lat, lon) travelling distance_m on a great circle."""
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    theta = math.radians(bearing_deg)
    delta = distance_m / EARTH_RADIUS_M

    lat2 = math.asin(
        math.sin(lat1) * math.cos(delta)
        + math.cos(lat1) * math.sin(delta) * math.cos(theta)
    )
    lon2 = lon1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(lat1),
        math.cos(delta) - math.sin(lat1) * math.sin(lat2),
    )
    return round(math.degrees(lat2), 6), round((math.degrees(lon2) + 540) % 360 - 180, 6)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (used only to self-check the output)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def _stamp(seconds: float) -> str:
    return (BASE_TIME + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# the clean track everything else is built from
# --------------------------------------------------------------------------
def make_clean_track(
    icao24: str = "a1b2c3",
    callsign: str = "SKY101",
    lat: float = LYH_LAT,
    lon: float = LYH_LON,
    heading_deg: float = 45.0,
    speed_kt: float = 450.0,
    altitude_ft: float = 35000.0,
    vertical_rate_fpm: float = 0.0,
    turn_rate_dps: float = 0.0,
    n_points: int = 40,
    interval_s: float = 5.0,
    start_s: float = 0.0,
    nic: int = 8,
    nacp: int = 9,
    label: str = "ok",
) -> list[dict[str, Any]]:
    """A believable flight: constant speed, optional steady turn and climb."""
    rows: list[dict[str, Any]] = []
    cur_lat, cur_lon = lat, lon
    cur_alt = altitude_ft
    cur_hdg = heading_deg

    for i in range(n_points):
        rows.append(
            {
                "_label": label,
                "icao24": icao24,
                "observed_at": _stamp(start_s + i * interval_s),
                "latitude": cur_lat,
                "longitude": cur_lon,
                "altitude_ft": round(cur_alt, 1),
                "ground_speed_kt": round(speed_kt, 1),
                "track_deg": round(cur_hdg % 360.0, 1),
                "vertical_rate_fpm": round(vertical_rate_fpm, 1),
                "nic": nic,
                "nacp": nacp,
                "callsign": callsign,
                "receiver_id": "lyh-01",
            }
        )
        step_m = speed_kt * KT_TO_MS * interval_s
        cur_lat, cur_lon = destination(cur_lat, cur_lon, cur_hdg, step_m)
        cur_alt += vertical_rate_fpm * (interval_s / 60.0)
        cur_hdg += turn_rate_dps * interval_s

    return rows


# --------------------------------------------------------------------------
# positives — each must produce a detection
# --------------------------------------------------------------------------
def inject_teleport(track, index: int = 20, jump_nm: float = 47.3):
    """Displace one point so reaching it would need thousands of knots."""
    rows = [dict(r) for r in track]
    row = rows[index]
    row["latitude"], row["longitude"] = destination(
        row["latitude"], row["longitude"], 90.0, jump_nm / M_TO_NM
    )
    row["_label"] = "positive:teleport_v1"
    row["_note"] = f"moved {jump_nm} nm sideways; implied speed is impossible"
    return rows


def inject_speed_contradiction(track, start: int = 10, end: int = 25, factor: float = 0.68):
    """Keep the positions honest, understate the reported ground speed."""
    rows = [dict(r) for r in track]
    for row in rows[start:end]:
        row["ground_speed_kt"] = round(row["ground_speed_kt"] * factor, 1)
        row["_label"] = "positive:speed_delta_v1"
        row["_note"] = "reported speed disagrees with the positions by ~32%"
    return rows


def inject_vrate_contradiction(track, start: int = 10, end: int = 25):
    """Report a hard climb while the altitude stays flat."""
    rows = [dict(r) for r in track]
    for row in rows[start:end]:
        row["vertical_rate_fpm"] = 3500.0
        row["_label"] = "positive:vrate_delta_v1"
        row["_note"] = "claims +3500 fpm while altitude is unchanged"
    return rows


def inject_impossible_turn(track, index: int = 20, turn_deg: float = 95.0):
    """One reported heading jump far beyond what an airframe can do."""
    rows = [dict(r) for r in track]
    rows[index]["track_deg"] = round((rows[index]["track_deg"] + turn_deg) % 360.0, 1)
    rows[index]["_label"] = "positive:turn_rate_v1"
    rows[index]["_note"] = f"{turn_deg} deg of heading change in 5 s = 19 deg/s"
    return rows


def inject_impersonation():
    """Two aircraft far apart broadcasting one ID, interleaved in time.

    Sorted by time this looks like ping-ponging: every hop is impossible and
    the direction reverses each time.
    """
    a = make_clean_track(
        icao24="a1b2c3", callsign="SKY101",
        lat=37.20, lon=-79.90, heading_deg=60.0,
        n_points=12, interval_s=10.0, start_s=0.0,
        label="positive:identity_coexistence",
    )
    b = make_clean_track(
        icao24="a1b2c3", callsign="SKY101",
        lat=38.60, lon=-77.30, heading_deg=200.0,
        n_points=12, interval_s=10.0, start_s=5.0,
        label="positive:identity_coexistence",
    )
    for row in a:
        row["_note"] = "transmitter A, south-west"
    for row in b:
        row["_note"] = (
            "transmitter B, north-east, same icao24; note this also trips the "
            "physics gates, which is expected — the ping-pong pattern is what "
            "separates impersonation from a one-way jump"
        )
    return sorted(a + b, key=lambda r: r["observed_at"])


def inject_gap_takeover(track, gap_start: int = 18, gap_points: int = 8, jump_nm: float = 120.0):
    """Silence, then the track resumes somewhere it could not have reached."""
    head = [dict(r) for r in track[:gap_start]]
    tail = [dict(r) for r in track[gap_start + gap_points:]]
    shifted = []
    for row in tail:
        row = dict(row)
        row["latitude"], row["longitude"] = destination(
            row["latitude"], row["longitude"], 315.0, jump_nm / M_TO_NM
        )
        row["_label"] = "positive:reappear_v1"
        row["_note"] = f"reappears {jump_nm} nm off-track after a 40 s gap"
        shifted.append(row)
    return head + shifted


def inject_integrity_collapse(track, start: int = 12, end: int = 30):
    """Sustained loss of navigation integrity — the GNSS-jamming signature."""
    rows = [dict(r) for r in track]
    for row in rows[start:end]:
        row["nic"] = 0
        row["nacp"] = 0
        row["_label"] = "positive:nic_floor_v1"
        row["_note"] = "navigation integrity pinned at 0 for 90 s"
    return rows


def inject_registry_mismatch(track):
    """A light-aircraft registration flying a jet profile."""
    rows = [dict(r) for r in track]
    for row in rows:
        row["icao24"] = "a7f3d1"
        row["callsign"] = "N412TB"
        row["_label"] = "positive:registry_mismatch_v1"
        row["_note"] = "registry says single-engine piston; profile is FL350 at 450 kt"
    return rows


# --------------------------------------------------------------------------
# negatives — each must produce NO detection
# --------------------------------------------------------------------------
def make_tailwind_cruise():
    """780 kt over the ground: unusual, entirely real in a jet stream."""
    rows = make_clean_track(
        icao24="ad4e21", callsign="JET778", speed_kt=780.0,
        altitude_ft=39000.0, n_points=30, label="negative:teleport_v1",
    )
    for row in rows:
        row["_note"] = "strong tailwind; below the 1000 kt gate"
    return rows


def make_standard_turn():
    """A normal rate-one turn at 3 deg/s."""
    rows = make_clean_track(
        icao24="a90b17", callsign="RGN220", speed_kt=280.0,
        altitude_ft=12000.0, turn_rate_dps=3.0, n_points=30,
        label="negative:turn_rate_v1",
    )
    for row in rows:
        row["_note"] = "standard rate turn; below the 10 deg/s gate"
    return rows


def make_legal_descent():
    """A steep but ordinary descent, with the reported rate matching."""
    rows = make_clean_track(
        icao24="a33c08", callsign="DAL915", speed_kt=320.0,
        altitude_ft=24000.0, vertical_rate_fpm=-3000.0, n_points=30,
        label="negative:vrate_delta_v1",
    )
    for row in rows:
        row["_note"] = "-3000 fpm, and the altitudes agree with it"
    return rows


def make_benign_gap():
    """Two minutes of silence, then the aircraft resumes where expected."""
    head = make_clean_track(
        icao24="a5d922", callsign="PDT440", n_points=18,
        label="negative:reappear_v1",
    )
    last = head[-1]
    resume_lat, resume_lon = destination(
        last["latitude"], last["longitude"], 45.0, 450.0 * KT_TO_MS * 120.0
    )
    tail = make_clean_track(
        icao24="a5d922", callsign="PDT440",
        lat=resume_lat, lon=resume_lon, n_points=18,
        start_s=18 * 5.0 + 120.0, label="negative:reappear_v1",
    )
    rows = head + tail
    for row in rows:
        row["_note"] = "120 s out of receiver range; returns inside the reachable circle"
    return rows


def make_close_formation():
    """Two different aircraft flying close together — not one spoofed ID."""
    a = make_clean_track(
        icao24="a11111", callsign="EVAC01", lat=37.50, lon=-79.00, n_points=20,
        label="negative:identity_coexistence",
    )
    b = make_clean_track(
        icao24="a22222", callsign="EVAC02", lat=37.505, lon=-79.004, n_points=20,
        label="negative:identity_coexistence",
    )
    for row in a + b:
        row["_note"] = "distinct icao24 values; proximity is not an identity finding"
    return sorted(a + b, key=lambda r: r["observed_at"])


def make_brief_nic_dip():
    """Integrity dips for 20 s and recovers — equipment, not jamming."""
    rows = make_clean_track(
        icao24="a6c440", callsign="UAL221", n_points=30,
        label="negative:nic_floor_v1",
    )
    for row in rows[10:14]:
        row["nic"] = 1
        row["nacp"] = 2
        row["_note"] = "20 s dip, then recovery; below the sustained-duration gate"
    return rows


def make_ground_vehicle():
    """An airport service vehicle: slow, on the ground, erratic heading."""
    rows = make_clean_track(
        icao24="a8ff02", callsign="OPS12", lat=37.3255, lon=-79.2004,
        speed_kt=12.0, altitude_ft=940.0, turn_rate_dps=2.0,
        n_points=20, interval_s=5.0, label="negative:ground_vehicle",
    )
    for row in rows:
        row["_note"] = (
            "surface vehicle at KLYH field elevation (~938 ft); AdsbObservation "
            "carries no on-ground flag, so judge it by altitude and speed"
        )
    return rows


def make_sparse_track():
    """Only two messages, 4 s apart. Too little evidence — abstain."""
    rows = make_clean_track(
        icao24="a0be55", callsign="N7714Q", speed_kt=110.0,
        altitude_ft=4500.0, n_points=2, interval_s=4.0,
        label="negative:insufficient_evidence",
    )
    for row in rows:
        row["_note"] = "2 observations only; the detector should abstain"
    return rows


# --------------------------------------------------------------------------
# write + self-check
# --------------------------------------------------------------------------
def implied_speeds_kt(rows):
    """Implied ground speed between consecutive rows of one aircraft."""
    out = []
    by_id: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_id.setdefault(row["icao24"], []).append(row)
    for track in by_id.values():
        track.sort(key=lambda r: r["observed_at"])
        for prev, cur in zip(track, track[1:]):
            t0 = datetime.fromisoformat(prev["observed_at"].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(cur["observed_at"].replace("Z", "+00:00"))
            dt = (t1 - t0).total_seconds()
            if dt <= 0:
                continue
            d = haversine_m(prev["latitude"], prev["longitude"],
                            cur["latitude"], cur["longitude"])
            out.append(d / dt / KT_TO_MS)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    clean = make_clean_track()

    files = {
        # negatives / baseline
        "clean_track.json": clean,
        "neg_tailwind_cruise.json": make_tailwind_cruise(),
        "neg_standard_turn.json": make_standard_turn(),
        "neg_legal_descent.json": make_legal_descent(),
        "neg_benign_gap.json": make_benign_gap(),
        "neg_close_formation.json": make_close_formation(),
        "neg_brief_nic_dip.json": make_brief_nic_dip(),
        "neg_ground_vehicle.json": make_ground_vehicle(),
        "neg_sparse_track.json": make_sparse_track(),
        # positives
        "pos_teleport.json": inject_teleport(clean),
        "pos_speed_contradiction.json": inject_speed_contradiction(clean),
        "pos_vrate_contradiction.json": inject_vrate_contradiction(clean),
        "pos_impossible_turn.json": inject_impossible_turn(clean),
        "pos_impersonation.json": inject_impersonation(),
        "pos_gap_takeover.json": inject_gap_takeover(clean),
        "pos_integrity_collapse.json": inject_integrity_collapse(clean),
        "pos_registry_mismatch.json": inject_registry_mismatch(clean),
    }

    for name, rows in files.items():
        path = OUT_DIR / name
        path.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        speeds = implied_speeds_kt(rows)
        peak = max(speeds) if speeds else 0.0
        print(f"{name:34s} {len(rows):4d} rows   peak implied {peak:9.1f} kt")


if __name__ == "__main__":
    main()
