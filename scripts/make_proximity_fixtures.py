"""Generate the synthetic proximity fixtures in air/fixtures/proximity_*.json.

Real dangerous-proximity events are rare and nobody labels them, so we script
encounters where the answer is known BY CONSTRUCTION: we choose where each
pair will be at closest approach, then run the clock backwards to get their
starting points. Every scenario reports at irregular, non-matching timestamps
on purpose — that is what real ADS-B looks like and what tracks.py must fix.

Run from the repo root:  python scripts/make_proximity_fixtures.py
Deterministic: same output every time (no randomness).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "air" / "fixtures"
REF_LAT, REF_LON = 37.4138, -79.1422  # Lynchburg, VA
T0 = datetime(2026, 9, 1, 0, 30, 0, tzinfo=timezone.utc)
R = 6_371_000.0
M_PER_NM = 1852.0
KT = M_PER_NM / 3600.0

# Two irregular report schedules (seconds after T0) that never coincide.
TIMES_A = [0.0, 2.3, 4.9, 7.6, 9.8, 12.4, 15.1, 17.7, 20.0]
TIMES_B = [1.1, 3.4, 6.2, 8.7, 11.3, 13.9, 16.5, 19.2]


def _xy_to_latlon(x_m: float, y_m: float) -> tuple[float, float]:
    lat = REF_LAT + math.degrees(y_m / R)
    lon = REF_LON + math.degrees(x_m / (R * math.cos(math.radians(REF_LAT))))
    return round(lat, 6), round(lon, 6)


def _vel(speed_kt: float, track_deg: float) -> tuple[float, float]:
    th = math.radians(track_deg)
    return speed_kt * KT * math.sin(th), speed_kt * KT * math.cos(th)


def _aircraft(
    icao: str,
    callsign: str,
    cpa_xy_nm: tuple[float, float],
    cpa_s: float,
    speed_kt: float,
    track_deg: float,
    alt_ft: float,
    times: list[float],
    label: str,
    vrate_fpm: float = 0.0,
) -> list[dict]:
    """Rows for one aircraft that will be at ``cpa_xy_nm`` at ``cpa_s`` seconds."""
    vx, vy = _vel(speed_kt, track_deg)
    x0 = cpa_xy_nm[0] * M_PER_NM - vx * cpa_s
    y0 = cpa_xy_nm[1] * M_PER_NM - vy * cpa_s
    rows = []
    for t in times:
        lat, lon = _xy_to_latlon(x0 + vx * t, y0 + vy * t)
        rows.append(
            {
                "_label": label,
                "icao24": icao,
                "observed_at": (T0 + timedelta(seconds=t)).isoformat().replace("+00:00", "Z"),
                "latitude": lat,
                "longitude": lon,
                "altitude_ft": round(alt_ft + vrate_fpm * t / 60.0, 1),
                "ground_speed_kt": speed_kt,
                "track_deg": track_deg,
                "vertical_rate_fpm": vrate_fpm,
                "nic": 8,
                "nacp": 9,
                "callsign": callsign,
            }
        )
    return rows


SCENARIOS = {
    # Head-on at 10,000 ft: at t=60 s they pass 0.2 nm apart laterally, 200 ft
    # vertically. Predicted separation is well inside HIGH the whole time.
    "proximity_head_on.json": {
        "_expect": {"detections": 1, "severity": "HIGH", "t_cpa_at_start_s": 60},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 10000, TIMES_A, "head_on_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 60, 300, 270, 10200, TIMES_B, "head_on_B"),
    },
    # Same geometry but headings reversed: they were closest 60 s AGO and are
    # now flying apart. t_cpa is negative -> no detection.
    "proximity_diverging.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), -60, 300, 90, 10000, TIMES_A, "diverging_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), -60, 300, 270, 10200, TIMES_B, "diverging_B"),
    },
    # Head-on horizontally but 2,500 ft apart vertically: the cheap vertical
    # prefilter drops the pair before any CPA math runs.
    "proximity_stacked.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 10000, TIMES_A, "stacked_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 60, 300, 270, 12500, TIMES_B, "stacked_B"),
    },
    # Right-angle crossing: predicted 2.0 nm horizontal, 500 ft vertical at
    # closest approach -> LOW (inside 3 nm / 1000 ft, outside MEDIUM's 1.5 nm).
    "proximity_crossing_low.json": {
        "_expect": {"detections": 1, "severity": "LOW", "t_cpa_at_start_s": 60},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 30000, TIMES_A, "crossing_A")
        + _aircraft(
            "bbb002", "TEST02", (2.0 / math.sqrt(2), 2.0 / math.sqrt(2)), 60, 300, 0, 30500, TIMES_B, "crossing_B"
        ),
    },
    # Two aircraft taxiing toward each other at Lynchburg (field elevation
    # 938 ft MSL). Metres apart, but on the ground -> no detection.
    "proximity_ground.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 15, 90, 940, TIMES_A, "taxi_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.02), 60, 20, 270, 940, TIMES_B, "taxi_B"),
    },
}


def main() -> None:
    for name, scenario in SCENARIOS.items():
        rows = [{"_expect": scenario["_expect"], **rows} if i == 0 else rows for i, rows in enumerate(scenario["rows"])]
        (FIXTURES / name).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
