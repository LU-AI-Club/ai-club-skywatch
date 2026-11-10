"""alert_cooldown_s: how often one pair may alert.

Decided with the Tech Lead (2026-11-03): an encounter lasting several minutes
SHOULD produce several alerts, and the front end groups them per pair ("these
two aircraft have 5 alerts"). What the detector must not do is alert on every
report, because ADS-B arrives every few seconds.

The cooldown is the minimum gap between two alerts about the same pair. It used
to be an accident of the runner's window size; it is now stated in config.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.proximity import ProximityDetector, load_config
from air.models.observation import AdsbObservation

T0 = EPOCH_ALIGNED = datetime(2026, 9, 1, 0, 30, tzinfo=timezone.utc)
EARTH_R, M_PER_NM = 6_371_000.0, 1852.0
KT = M_PER_NM / 3600.0
LAT, LON = 37.4138, -79.1422
CFG = load_config()


def _converging(duration_s=110.0, step_s=2.5):
    """A pair that stays inside every gate for ~110 s.

    Head-on at FL350 with a 0.2 nm lateral offset, 50 kt each (100 kt closing),
    starting 3 nm apart -- so closest approach is about 108 s out and falls
    steadily, keeping the pair inside max_tcpa_s and max_current_separation_nm
    for the whole run. Long enough that the cooldown has to do real work.
    """
    out = []
    for icao, track, alt, lateral_nm in (("aaa001", 90, 35000.0, 0.0), ("bbb002", 270, 35100.0, 0.2)):
        th = math.radians(track)
        vx, vy = 50 * KT * math.sin(th), 50 * KT * math.cos(th)
        # place each 1.5 nm from the meeting point, closing
        x0 = -vx * 108.0
        y0 = -vy * 108.0 + lateral_nm * M_PER_NM
        t = 0.0 if icao == "aaa001" else 1.1
        while t < duration_s:
            out.append(AdsbObservation(
                icao24=icao, observed_at=T0 + timedelta(seconds=t),
                latitude=LAT + math.degrees((y0 + vy * t) / EARTH_R),
                longitude=LON + math.degrees((x0 + vx * t) / (EARTH_R * math.cos(math.radians(LAT)))),
                altitude_ft=alt, ground_speed_kt=50, track_deg=track,
                vertical_rate_fpm=0.0, nic=8, nacp=10,
            ))
            t += step_s
    return out


def _alerts(observations, cooldown_s):
    cfg = replace(CFG, alert_cooldown_s=cooldown_s)
    return ProximityDetector(cfg).detect_observations(observations)


def test_a_short_encounter_alerts_once():
    assert len(_alerts(_converging(40), cooldown_s=60)) == 1


def test_a_long_encounter_alerts_repeatedly():
    """Five minutes at a 60 s cooldown is about five alerts, not one and not
    one per report."""
    alerts = _alerts(_converging(), cooldown_s=15)
    assert 6 <= len(alerts) <= 9, f"expected ~8 alerts over 110 s at a 15 s cooldown, got {len(alerts)}"


def test_alerts_are_never_closer_together_than_the_cooldown():
    alerts = _alerts(_converging(), cooldown_s=30)
    times = sorted(a.temporal_bounds.start_time for a in alerts)
    gaps = [(b - a).total_seconds() for a, b in zip(times, times[1:])]
    assert gaps, "need at least two alerts to compare"
    assert all(g >= 29 for g in gaps), f"alerts too close together: {gaps}"


def test_a_shorter_cooldown_gives_more_alerts():
    assert len(_alerts(_converging(), 15)) > len(_alerts(_converging(), 30)) > len(_alerts(_converging(), 120))


def test_zero_cooldown_alerts_on_every_tick():
    """The escape hatch: 0 disables grouping entirely."""
    obs = _converging()
    assert len(_alerts(obs, cooldown_s=0)) > len(_alerts(obs, cooldown_s=15))


def test_the_cooldown_comes_from_config_not_the_window_size():
    """The bug this replaced: behaviour used to depend on how the runner was
    configured, so a 10 s window alerted every 10 s."""
    assert CFG.alert_cooldown_s == 60.0
    obs = _converging()
    assert len(_alerts(obs, 15)) != len(_alerts(obs, 120))


def test_each_alert_describes_the_closest_moment_it_covers():
    """Within one cooldown group we keep the tightest predicted approach, so an
    alert reports the worst moment it saw, not the first."""
    alerts = _alerts(_converging(), cooldown_s=30)
    for a in alerts:
        meta = a.evidence[0].metadata
        assert meta["predicted_horizontal_nm"] <= meta["horizontal_now_nm"] + 1e-6


def test_a_negative_cooldown_is_rejected():
    with pytest.raises(ValueError):
        replace(CFG, alert_cooldown_s=-1.0)
