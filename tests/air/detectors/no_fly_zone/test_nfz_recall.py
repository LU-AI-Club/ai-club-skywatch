"""Recall tests: scripted incursions with known answers, on the real FAA zones.

The rest of the suite mostly checks single stages, or checks that we stay quiet
when we should. A replay of one real Lynchburg hour gave 2 detections (both LOW,
in a MOA) and never touched R-6602 or P-56, so real traffic alone cannot tell us
whether the detector catches a real violation. These tests do: each one flies a
straight track through a real zone in ``klyh-local-faa.geojson``, sends it in
through the shared-runner route (``AdsbObservation`` -> ``detect_observations``
-> ``flush``), and checks what comes out.

Four groups:

* **Must catch**: violations the detector has to flag. A miss here is a bug.
* **Must stay quiet**: look-alikes that are not violations.
* **Severity as designed**: cases that fire, but on purpose not as HIGH.
  These pin current policy so a change to it is deliberate.
* **Known blind spots**: ``xfail(strict=True)``. Each states what we would
  want, and its reason names what is missing. When that is fixed the test
  XPASSes, fails the run, and the marker gets removed.

Results and discussion: docs/no_fly_zone/RECALL_ANALYSIS.md.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest
from nfz_support import FIXTURES

from air.detectors.no_fly_zone import build_detector
from air.models.observation import AdsbObservation
from contracts import Detection, SeverityLevel

LIVE_AIRSPACE = FIXTURES / "airspace" / "klyh-local-faa.geojson"

EARTH_R_M = 6_371_000.0
M_PER_NM = 1852.0

# A point inside each zone (shapely representative_point of the live geometry).
P56A = (38.8924, -77.0265)       # P-56: the White House / National Mall, ~2.7 x 1.2 nm
P56B = (38.9214, -77.0669)       # P-56 #2: Naval Observatory, ~0.9 nm across
FORT_PICKETT = (37.0297, -77.9108)  # R-6602A/B/C stacked, under the Barfoot MOAs
FARMVILLE = (37.1798, -78.5182)  # Farmville MOA, terrain ~516 ft MSL here

# Times chosen against each zone's published schedule.
NOV_TUE_10L = datetime(2026, 11, 17, 15, 0, tzinfo=UTC)  # Tue 10:00 EST
JUL_TUE_11L = datetime(2026, 7, 14, 15, 0, tzinfo=UTC)   # Tue 11:00 EDT, R-6602A season

# readsb ADS-B is ~1 Hz; the live poller samples the feed every 10 s by default
# (SKYWATCH_ADSB_POLL_SECONDS), which is the sparsest cadence NFZ sees live.
LIVE_POLL_S = 10.0


def crossing(
    center: tuple[float, float],
    *,
    alt_ft: float | None,
    speed_kt: float = 120.0,
    heading_deg: float = 90.0,
    start: datetime = NOV_TUE_10L,
    step_s: float = 1.0,
    half_length_nm: float = 6.0,
    geom_offset_ft: float = 0.0,
    baro: bool = True,
    geom: bool = True,
    icao24: str = "a1b2c3",
    callsign: str | None = "N123AB",
    squawk: str | None = "1200",
    on_ground: bool = False,
) -> list[AdsbObservation]:
    """A straight, level track that passes through ``center``.

    Starts ``half_length_nm`` before the point and ends the same distance past
    it, so it begins and ends outside any zone it crosses. ``alt_ft`` is the
    barometric value; geometric is ``alt_ft + geom_offset_ft``.
    """
    lat0, lon0 = center
    speed_ms = speed_kt * M_PER_NM / 3600.0
    heading = math.radians(heading_deg)
    duration_s = 2 * half_length_nm * M_PER_NM / speed_ms
    out: list[AdsbObservation] = []
    t = 0.0
    while t <= duration_s:
        along_m = -half_length_nm * M_PER_NM + speed_ms * t
        lat = lat0 + math.degrees(along_m * math.cos(heading) / EARTH_R_M)
        lon = lon0 + math.degrees(
            along_m * math.sin(heading) / (EARTH_R_M * math.cos(math.radians(lat0)))
        )
        out.append(
            AdsbObservation(
                icao24=icao24,
                observed_at=start + timedelta(seconds=t),
                latitude=lat,
                longitude=lon,
                altitude_ft=alt_ft if (baro and alt_ft is not None) else None,
                alt_geom_ft=(alt_ft + geom_offset_ft) if (geom and alt_ft is not None) else None,
                ground_speed_kt=speed_kt,
                track_deg=heading_deg,
                nic=8,
                nacp=9,
                squawk=squawk,
                callsign=callsign,
                on_ground=on_ground,
                source_row_id=f"recall:{icao24}:{t:.0f}",
            )
        )
        t += step_s
    return out


def detect(observations: Sequence[AdsbObservation]) -> list[Detection]:
    """Run the observations through a fresh detector on the real FAA zones."""
    detector = build_detector(airspace_path=LIVE_AIRSPACE)
    return detector.detect_observations(list(observations)) + detector.flush()


def zone_of(detection: Detection) -> str:
    return str(detection.metadata["extras"]["zone_id"])


def in_zone(detections: Sequence[Detection], zone_id: str) -> list[Detection]:
    return [d for d in detections if zone_of(d) == zone_id]


# --- Must catch ------------------------------------------------------------------

@pytest.mark.parametrize("step_s", [1.0, LIVE_POLL_S], ids=["1Hz", "live-poll-10s"])
@pytest.mark.parametrize(
    "alt_ft, speed_kt",
    [
        (500, 60),      # helicopter, low and slow
        (1500, 120),    # light aircraft
        (5000, 180),
        (10000, 250),   # 250 kt is the speed limit below 10,000 ft
        (17800, 300),   # just under the 18,000 ft MSL ceiling
    ],
)
def test_p56_crossing_is_caught_as_high(alt_ft: float, speed_kt: float, step_s: float) -> None:
    hits = in_zone(detect(crossing(P56A, alt_ft=alt_ft, speed_kt=speed_kt, step_s=step_s)), "P-56")
    assert len(hits) == 1, f"expected one P-56 incursion at {alt_ft} ft / {speed_kt} kt"
    assert hits[0].severity is SeverityLevel.HIGH


@pytest.mark.parametrize("heading_deg", [0.0, 90.0, 45.0])
def test_p56_crossing_is_caught_from_any_direction(heading_deg: float) -> None:
    hits = in_zone(detect(crossing(P56A, alt_ft=1500, heading_deg=heading_deg)), "P-56")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.HIGH


@pytest.mark.parametrize("speed_kt", [120.0, 250.0, 350.0])
def test_smallest_zone_is_caught_at_live_poll_cadence(speed_kt: float) -> None:
    """P-56B is ~0.9 nm across. At 350 kt and one report every 10 s an aircraft
    moves ~1 nm between reports, so this is close to the sampling limit."""
    obs = crossing(P56B, alt_ft=3000, speed_kt=speed_kt, step_s=LIVE_POLL_S)
    hits = in_zone(detect(obs), "P-56 #2")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.HIGH


def test_barometric_only_aircraft_is_still_caught() -> None:
    """No geometric altitude: NFZ falls back to barometric and says so."""
    hits = in_zone(detect(crossing(P56A, alt_ft=1500, geom=False)), "P-56")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.HIGH
    assert any("Barometric altitude was used" in lim for lim in hits[0].metadata["limitations"])


def test_r6602a_in_season_is_caught_as_high() -> None:
    """R-6602A (SFC-4,000 MSL) is published active May 1 - Sep 15."""
    hits = in_zone(detect(crossing(FORT_PICKETT, alt_ft=2500, start=JUL_TUE_11L)), "R-6602A")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.HIGH


def test_loitering_inside_p56_is_one_detection() -> None:
    """Three minutes circling inside the zone: one incursion, not 180."""
    lat0, lon0 = P56A
    obs = [
        AdsbObservation(
            icao24="d00d01",
            observed_at=NOV_TUE_10L + timedelta(seconds=t),
            latitude=lat0 + 0.003 * math.cos(math.radians(2 * t)),
            longitude=lon0 + 0.004 * math.sin(math.radians(2 * t)),
            altitude_ft=800,
            alt_geom_ft=800,
            ground_speed_kt=40,
            nic=8,
            nacp=9,
            on_ground=False,
            source_row_id=f"recall:loiter:{t}",
        )
        for t in range(180)
    ]
    hits = in_zone(detect(obs), "P-56")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.HIGH


def test_leaving_and_coming_back_is_two_detections() -> None:
    out_and_back = crossing(P56A, alt_ft=1500) + crossing(
        P56A, alt_ft=1500, heading_deg=270, start=NOV_TUE_10L + timedelta(minutes=10)
    )
    assert len(in_zone(detect(out_and_back), "P-56")) == 2


# --- Must stay quiet -------------------------------------------------------------

def test_overflight_above_p56_ceiling_is_quiet() -> None:
    assert detect(crossing(P56A, alt_ft=18200, speed_kt=300)) == []


def test_overflight_above_r6602c_is_quiet() -> None:
    assert detect(crossing(FORT_PICKETT, alt_ft=20000, speed_kt=300, start=JUL_TUE_11L)) == []


def test_pass_one_nm_clear_of_p56b_is_quiet() -> None:
    clear = (P56B[0] + 1.0 / 60.0, P56B[1])  # 1 nm north of the centre, ~0.55 nm outside
    assert detect(crossing(clear, alt_ft=1500)) == []


def test_aircraft_on_the_ground_is_quiet() -> None:
    assert detect(crossing(P56A, alt_ft=0, speed_kt=20, half_length_nm=1.0, on_ground=True)) == []


def test_below_a_moa_agl_floor_is_quiet() -> None:
    """Farmville MOA floor is 300 ft AGL; terrain here is ~516 ft MSL."""
    obs = crossing(FARMVILLE, alt_ft=516 + 150, half_length_nm=3.0)
    assert in_zone(detect(obs), "FARMVILLE MOA") == []


# --- Severity as designed ----------------------------------------------------------

def test_r6602a_out_of_season_is_capped_at_low() -> None:
    """Outside May 1 - Sep 15 R-6602A is "BY NOTAM". With no NOTAM feed its
    activation is UNKNOWN, which caps severity at LOW (severity.unknown_activation_cap)."""
    hits = in_zone(detect(crossing(FORT_PICKETT, alt_ft=2500)), "R-6602A")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.LOW


@pytest.mark.parametrize("zone_id, alt_ft", [("R-6602B", 6000), ("R-6602C", 14000)])
def test_notam_only_restricted_areas_never_exceed_low(zone_id: str, alt_ft: float) -> None:
    for when in (NOV_TUE_10L, JUL_TUE_11L):
        hits = in_zone(detect(crossing(FORT_PICKETT, alt_ft=alt_ft, start=when)), zone_id)
        assert len(hits) == 1 and hits[0].severity is SeverityLevel.LOW


def test_one_fort_pickett_crossing_also_reports_the_moas_above_it() -> None:
    """Zones overlap here. One low crossing is one HIGH (R-6602A) plus a LOW
    for each Barfoot MOA the track passes through: several rows for one flight."""
    found = detect(crossing(FORT_PICKETT, alt_ft=2500, start=JUL_TUE_11L))
    assert {zone_of(d) for d in found} == {"R-6602A", "BARFOOT 1 MOA", "BARFOOT 2 MOA"}
    assert [d.severity for d in in_zone(found, "R-6602A")] == [SeverityLevel.HIGH]


def test_moa_is_low_on_and_off_its_published_hours() -> None:
    weekday = detect(crossing(FARMVILLE, alt_ft=3000, half_length_nm=3.0))
    saturday = detect(
        crossing(FARMVILLE, alt_ft=3000, half_length_nm=3.0, start=NOV_TUE_10L + timedelta(days=4))
    )
    for found in (weekday, saturday):
        hits = in_zone(found, "FARMVILLE MOA")
        assert len(hits) == 1 and hits[0].severity is SeverityLevel.LOW


def test_clipping_the_edge_inside_position_uncertainty_is_info() -> None:
    """A chord 0.45 nm off P-56B's centre stays just outside the polygon but
    within the position-uncertainty buffer: possibly a violation, possibly
    position error, so INFO (severity.buffered_only)."""
    edge = (P56B[0] + 0.45 / 60.0, P56B[1])
    hits = in_zone(detect(crossing(edge, alt_ft=1500)), "P-56 #2")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.INFO


@pytest.mark.parametrize(
    "icao24, squawk, callsign",
    [
        ("a1b2c3", "4521", "N123AB"),       # discrete code: under ATC control
        ("a1b2c3", "1200", "LIFEGUARD1"),   # medevac
        ("ae1234", "1200", "N123AB"),       # US military ICAO block
        ("a1b2c3", "7700", "N123AB"),       # declared emergency
    ],
)
def test_context_lowers_the_score_but_not_the_severity(
    icao24: str, squawk: str, callsign: str
) -> None:
    """Context signals are subtracted from anomaly_score only. An authorised-looking
    flight through P-56 is still HIGH; the lower score is the only difference."""
    baseline = in_zone(detect(crossing(P56A, alt_ft=1500)), "P-56")[0]
    obs = crossing(P56A, alt_ft=1500, icao24=icao24, squawk=squawk, callsign=callsign)
    hits = in_zone(detect(obs), "P-56")
    assert len(hits) == 1 and hits[0].severity is SeverityLevel.HIGH
    assert hits[0].metadata["anomaly_score"] < baseline.metadata["anomaly_score"]


# --- Known blind spots -------------------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="geo/altitude.py: no altitude -> BAD_INPUT abstain, even inside a "
    "surface-up prohibited area. A position report with no altitude inside "
    "P-56 (SFC-18,000) produces nothing.",
)
def test_no_altitude_inside_surface_up_prohibited_area_is_flagged() -> None:
    hits = in_zone(detect(crossing(P56A, alt_ft=None)), "P-56")
    assert len(hits) == 1  # any severity: the point is that it surfaces at all


@pytest.mark.xfail(
    strict=True,
    reason="geo/altitude.py: geometric altitude is WGS84-ellipsoid height compared "
    "with MSL limits, no geoid correction. Around DC and Lynchburg the geoid is "
    "~33 m (~100 ft) below the ellipsoid, so geometric altitude reads ~100 ft "
    "low and an aircraft legally just above a ceiling looks inside.",
)
def test_aircraft_legally_above_p56_ceiling_is_not_flagged() -> None:
    # True altitude 18,050 ft MSL (legal); readsb geometric reads ~100 ft low.
    obs = crossing(P56A, alt_ft=18050, speed_kt=300, geom_offset_ft=-100)
    assert in_zone(detect(obs), "P-56") == []
