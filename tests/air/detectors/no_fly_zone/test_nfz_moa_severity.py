"""A MOA is context, never an alarm; "by NOTAM" hours are not known-active.

Two rules, checked on the real FAA zones the live detector loads:

* ``severity.zone_type_cap`` holds a zone type under a ceiling whatever its
  activation. Flying through a MOA is legal even while it is in use.
* Hours published as "BY NOTAM" or "INTERMITTENT" bound when a zone may be
  used. Inside them activation is UNKNOWN, not ACTIVE.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from nfz_support import FIXTURES, make_state

from air.detectors.no_fly_zone.config import Config, _validate, load_config
from air.detectors.no_fly_zone.geo.terrain import load_terrain
from air.detectors.no_fly_zone.ingest.airspace_loader import load_filtered_zones
from air.detectors.no_fly_zone.logic import detector as pipeline
from air.detectors.no_fly_zone.types import Severity
from scripts.make_faa_airspace import unknown_within_schedule_for

LIVE_AIRSPACE = FIXTURES / "airspace" / "klyh-local-faa.geojson"
TUESDAY_NOON_LOCAL = datetime(2026, 11, 17, 17, 0, tzinfo=UTC)
JULY_NOON_LOCAL = datetime(2026, 7, 14, 16, 0, tzinfo=UTC)


def _severity_in(zone_id: str, altitude_ft: float, when: datetime, cfg: Config) -> Severity:
    """Severity of one report strictly inside real zone ``zone_id``."""
    zones = load_filtered_zones(LIVE_AIRSPACE, cfg)
    zone = next(z for z in zones if z.zone_id == zone_id)
    point = zone.geometry.representative_point()
    state = make_state(
        lat=point.y, lon=point.x, alt_geom_ft=altitude_ft, alt_baro_ft=altitude_ft, timestamp=when
    )
    fired = pipeline.run([state], zones, cfg, terrain=load_terrain())
    [detection] = [d for d in fired if d.extras["zone_id"] == zone_id]
    return detection.severity


def _cfg_with_cap(cap: dict[str, str] | None) -> Config:
    raw = dict(load_config().raw)
    severity = dict(raw["severity"])
    severity.pop("zone_type_cap", None)
    if cap is not None:
        severity["zone_type_cap"] = cap
    raw["severity"] = severity
    return Config(raw)


def test_moa_in_its_published_hours_is_capped_at_low() -> None:
    """Farmville is known-active on a weekday noon, and still only LOW."""
    assert _severity_in("FARMVILLE MOA", 3000.0, TUESDAY_NOON_LOCAL, load_config()) is Severity.LOW


def test_without_the_cap_the_same_report_is_high() -> None:
    """The cap is what holds it down, not the schedule."""
    cfg = _cfg_with_cap(None)
    assert _severity_in("FARMVILLE MOA", 3000.0, TUESDAY_NOON_LOCAL, cfg) is Severity.HIGH


def test_the_cap_is_per_zone_type() -> None:
    cfg = _cfg_with_cap({"MOA": "MEDIUM"})
    assert _severity_in("FARMVILLE MOA", 3000.0, TUESDAY_NOON_LOCAL, cfg) is Severity.MEDIUM


def test_restricted_and_prohibited_areas_are_not_capped() -> None:
    cfg = load_config()
    assert _severity_in("R-6602A", 2000.0, JULY_NOON_LOCAL, cfg) is Severity.HIGH
    assert _severity_in("P-56", 3000.0, TUESDAY_NOON_LOCAL, cfg) is Severity.HIGH


@pytest.mark.parametrize("zone_id", ["EVERS SOUTH MOA", "BARFOOT 3 MOA"])
def test_by_notam_and_intermittent_moas_stay_low_even_uncapped(zone_id: str) -> None:
    """With no zone-type cap at all, these are held by unknown activation."""
    cfg = _cfg_with_cap(None)
    altitude_ft = 14000.0 if zone_id.startswith("EVERS") else 8000.0
    assert _severity_in(zone_id, altitude_ft, TUESDAY_NOON_LOCAL, cfg) is Severity.LOW


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("0630 - SUNSET, DAILY, BY NOTAM; OTHER TIMES BY NOTAM", True),
        ("INTERMITTENT, SUNRISE - SUNSET, DAILY", True),
        ("0800 - 1700, MON - FRI; O/T BY NOTAM", False),
        ("MAY 1 - SEP 15, CONTINUOUS; OTHER TIMES BY NOTAM 24 HRS IN ADVANCE", False),
        ("CONTINUOUS", False),
        (None, False),
    ],
)
def test_builder_flags_hours_that_only_bound_possible_use(text: Any, expected: bool) -> None:
    assert unknown_within_schedule_for(text) is expected


@pytest.mark.parametrize("cap", [{"MOA": "SEVERE"}, {"BALLOON": "LOW"}, ["MOA"]])
def test_config_rejects_a_bad_zone_type_cap(cap: Any) -> None:
    raw = dict(load_config().raw)
    raw["severity"] = {**raw["severity"], "zone_type_cap": cap}
    with pytest.raises(ValueError):
        _validate(raw)
