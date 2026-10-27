"""Recall tests: scripted collisions the detector MUST catch.

Every other test asks "do we stay quiet when we should?". After PROX-1, 2, 3 and
8 cut the Lynchburg hour from 1,128 detections to 3, the opposite question
matters more: **have we tuned ourselves blind?**

Each case below is an actual collision — two aircraft arriving at the same point
at the same moment. A detector that misses one of these is not conservative, it
is broken. The xfails record real blind spots found on 2026-10-27; each names the
gate responsible, and they flip to XPASS the moment that gate is reworked.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.proximity import ProximityDetector, load_config
from air.models.observation import AdsbObservation
from contracts import SeverityLevel

T0 = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)
EARTH_R = 6_371_000.0
M_PER_NM = 1852.0
KT = M_PER_NM / 3600.0
LAT, LON = 37.4138, -79.1422


def collision_track(icao, impact_s, speed_kt, track_deg, alt_ft, offset_s=0.0,
                    vrate_fpm=0.0, duration_s=300.0, step_s=2.5):
    """One aircraft that reaches (LAT, LON) exactly at ``impact_s``."""
    th = math.radians(track_deg)
    vx, vy = speed_kt * KT * math.sin(th), speed_kt * KT * math.cos(th)
    x0, y0 = -vx * impact_s, -vy * impact_s
    out = []
    t = offset_s
    while t < duration_s:
        out.append(AdsbObservation(
            icao24=icao,
            observed_at=T0 + timedelta(seconds=t),
            latitude=LAT + math.degrees((y0 + vy * t) / EARTH_R),
            longitude=LON + math.degrees((x0 + vx * t) / (EARTH_R * math.cos(math.radians(LAT)))),
            altitude_ft=alt_ft + vrate_fpm * t / 60.0,
            ground_speed_kt=speed_kt, track_deg=track_deg,
            vertical_rate_fpm=vrate_fpm, nic=8, nacp=9,
        ))
        t += step_s
    return out


def head_on(alt_ft, speed_kt, impact_s=300.0):
    return (collision_track("aaa001", impact_s, speed_kt, 90, alt_ft)
            + collision_track("bbb002", impact_s, speed_kt, 270, alt_ft, offset_s=1.1))


def detect(observations):
    return ProximityDetector().detect_observations(observations)


# --- Collisions we DO catch -----------------------------------------------------
@pytest.mark.parametrize("alt_ft, speed_kt", [
    (35000, 450),   # airliners head-on at cruise, 900 kt closure
    (10000, 450),
    (10000, 250),
    (10000, 110),   # light aircraft
    (5100, 250),    # just above the terminal floor
])
def test_head_on_collision_is_caught(alt_ft, speed_kt):
    d = detect(head_on(alt_ft, speed_kt))
    assert d, f"missed a collision at {alt_ft} ft, {speed_kt} kt each"
    assert d[0].severity is SeverityLevel.HIGH


def test_right_angle_collision_is_caught():
    d = detect(collision_track("aaa001", 300, 400, 90, 30000)
               + collision_track("bbb002", 300, 400, 180, 30000, offset_s=1.1))
    assert d and d[0].severity is SeverityLevel.HIGH


def test_overtaking_collision_is_caught():
    """Same direction, one faster. Low closure rate, still a collision."""
    d = detect(collision_track("aaa001", 300, 480, 90, 33000)
               + collision_track("bbb002", 300, 380, 90, 33000, offset_s=1.1))
    assert d and d[0].severity is SeverityLevel.HIGH


# --- Blind spots, pinned ---------------------------------------------------------
@pytest.mark.xfail(strict=True, reason="PROX-8: min_altitude_ft hides every collision below 5,000 ft")
@pytest.mark.parametrize("alt_ft, speed_kt", [(3000, 250), (4000, 110), (1500, 120)])
def test_low_altitude_collision_is_caught(alt_ft, speed_kt):
    assert detect(head_on(alt_ft, speed_kt))


def test_pure_vertical_convergence_is_caught():
    """Same track and speed, one climbing into the other. Horizontally they never
    move relative to each other (|v| is ~0), so time_to_cpa falls back to when
    the vertical gap closes."""
    d = detect(collision_track("aaa001", 300, 400, 90, 24000)
               + collision_track("bbb002", 300, 400, 90, 21000, offset_s=1.1, vrate_fpm=1000))
    assert d


@pytest.mark.xfail(strict=True, reason="t_cpa follows horizontal motion only, so a near-parallel "
                   "pair is judged at the horizontal closest point, not when the vertical gap closes")
@pytest.mark.parametrize("speed_b_kt", [401, 405])
def test_near_parallel_vertical_convergence_is_caught(speed_b_kt):
    """Same as above but B is 1-5 kt faster. The vertical gap closes at t=180 s,
    when they are 0.03-0.17 nm apart horizontally -- but any horizontal relative
    motion sends t_cpa to the horizontal formula (t=300 s), by which time B is
    2,000 ft above A, so nothing is flagged."""
    d = detect(collision_track("aaa001", 300, 400, 90, 24000)
               + collision_track("bbb002", 300, speed_b_kt, 90, 21000, offset_s=1.1, vrate_fpm=1000))
    assert d


# --- Warning time ------------------------------------------------------------------
def first_alert_lead_s(observations, impact_s=300.0):
    """Seconds between the first detection and impact."""
    from air.detectors.proximity import pair_geometry, flag_pair
    from air.detectors.proximity.tracks import align_tracks
    from air.detectors.proximity.pairs import candidate_pairs

    cfg = load_config()
    for tick, snap in align_tracks(observations, cfg).items():
        for a, b in candidate_pairs(snap, cfg):
            g = pair_geometry(a, b)
            if g and flag_pair(g, cfg):
                return impact_s - (tick - T0).total_seconds()
    return None


def test_fast_closure_warning_is_short_but_nonzero():
    """900 kt closure: max_current_separation_nm caps the warning at ~40 s,
    because the pair is further than 10 nm apart until then."""
    lead = first_alert_lead_s(head_on(35000, 450))
    assert lead is not None
    assert 30 <= lead <= 50, f"expected ~40 s of warning, got {lead}"


def test_slow_closure_gets_the_full_window():
    """220 kt closure stays inside 10 nm for long enough to use the whole
    120 s prediction horizon."""
    lead = first_alert_lead_s(head_on(10000, 110))
    assert lead is not None and lead >= 110
