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
# Same schedules shifted to 40-80 s, so the reports straddle T0 + 60 s
# (00:31:00), which is a boundary of the runner's epoch-anchored 60 s windows.
TIMES_A_EDGE = [40.0 + t * 2 for t in TIMES_A]
TIMES_B_EDGE = [40.0 + t * 2 for t in TIMES_B]


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
    # PROX-5: ONE head-on encounter whose 40 s of reports cross the 00:31:00
    # window edge. Closest approach at t=110 s, so it is converging and inside
    # max_tcpa_s in BOTH 60 s windows. One encounter -> one detection, however
    # the runner slices time.
    "proximity_spans_window.json": {
        "_expect": {"detections": 1, "severity": "HIGH", "window_edge_s": 60},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 110, 300, 90, 10000, TIMES_A_EDGE, "edge_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 110, 300, 270, 10200, TIMES_B_EDGE, "edge_B"),
    },
    # PROX-2: head-on at FL360/FL370, 0.2 nm apart laterally. They hold the
    # standard 1000 ft vertical separation, reported 975 ft because baro
    # altitudes jitter ~25 ft -> exactly as separated as ATC intends, no detection.
    # 7.5 nm apart now, so the PROX-1 distance gate is not what keeps it quiet.
    "proximity_standard_vertical.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 30, 450, 90, 36000, TIMES_A, "standard_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 30, 450, 270, 36975, TIMES_B, "standard_B"),
    },
    # PROX-2 counterpart: same geometry at FL360 but only 650 ft apart vertically
    # (well under standard) -> still fires, MEDIUM (inside 1.5 nm / 700 ft).
    "proximity_small_vertical_gap.json": {
        "_expect": {"detections": 1, "severity": "MEDIUM", "t_cpa_at_start_s": 30},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 30, 450, 90, 36000, TIMES_A, "gap_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 30, 450, 270, 36650, TIMES_B, "gap_B"),
    },
    # PROX-1: head-on and "converging" on paper (0.2 nm / 200 ft at closest
    # approach, 112 s out), but ~25 nm apart right now at 400 kt each. A one
    # degree track error moves each aircraft ~0.2 nm by then and real traffic
    # drifts far more, so the prediction isn't trustworthy -> no detection.
    "proximity_far_converging.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 112, 400, 90, 10000, TIMES_A, "far_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 112, 400, 270, 10200, TIMES_B, "far_B"),
    },
    # PROX-1 counterpart: same geometry at closest approach, but only 5 nm
    # apart now (30 s out). A genuine near-term close approach still fires.
    "proximity_near_term.json": {
        "_expect": {"detections": 1, "severity": "HIGH", "t_cpa_at_start_s": 30},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 30, 300, 90, 10000, TIMES_A, "near_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 30, 300, 270, 10200, TIMES_B, "near_B"),
    },
    # PROX-6: the head-on geometry exactly, but at 3,000 ft instead of 10,000.
    # Terminal airspace: close traffic there is routine and our constant-track
    # model does not hold, so the altitude floor suppresses it.
    "proximity_terminal_altitude.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 3000, TIMES_A, "terminal_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 60, 300, 270, 3200, TIMES_B, "terminal_B"),
    },
    # PROX-6 counterpart: identical geometry just above the floor -> still HIGH.
    "proximity_just_above_floor.json": {
        "_expect": {"detections": 1, "severity": "HIGH", "t_cpa_at_start_s": 60},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 5200, TIMES_A, "floor_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.2), 60, 300, 270, 5400, TIMES_B, "floor_B"),
    },
    # Two aircraft taxiing toward each other at Lynchburg (field elevation
    # 938 ft MSL). Metres apart, but on the ground -> no detection.
    "proximity_ground.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft("aaa001", "TEST01", (0.0, 0.0), 60, 15, 90, 940, TIMES_A, "taxi_A")
        + _aircraft("bbb002", "TEST02", (0.0, 0.02), 60, 20, 270, 940, TIMES_B, "taxi_B"),
    },

    # Regression: aircraft remain far apart at predicted closest approach.
    "proximity_far_apart.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft(
            "aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 10000, TIMES_A, "far_A"
        )
        + _aircraft(
            "bbb002", "TEST02", (0.0, 8.0), 60, 300, 270, 10200, TIMES_B, "far_B"
        ),
    },

    # Regression: close horizontal geometry below the 5,000 ft threshold.
    "proximity_below_5000ft.json": {
        "_expect": {"detections": 0},
        "rows": _aircraft(
            "aaa001", "TEST01", (0.0, 0.0), 60, 300, 90, 4000, TIMES_A, "low_A"
        )
        + _aircraft(
            "bbb002", "TEST02", (0.0, 0.2), 60, 300, 270, 4200, TIMES_B, "low_B"
        ),
    },

}


def main() -> None:
    for name, scenario in SCENARIOS.items():
        rows = [{"_expect": scenario["_expect"], **rows} if i == 0 else rows for i, rows in enumerate(scenario["rows"])]
        (FIXTURES / name).write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {name}: {len(rows)} rows")


if __name__ == "__main__":
    main()
