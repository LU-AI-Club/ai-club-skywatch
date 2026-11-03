"""Tests for reading an aircraft's own altitude resolution off its track.

Altitude arrives rounded, and transmitters do not all round the same way: in
one real hour 742 aircraft stepped by 25 ft and 31 by 100 ft. Assuming the
common value for a 100 ft reporter reads an honest 1,500 fpm climb as
12,121 fpm over half a second, which was most of the remaining climb-rate
false alerts.

Inferring too eagerly is the opposite failure: a wide step means a wide
allowance, and a wide allowance hides real lies. The cases below pin both
directions.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.features import infer_altitude_quantum_ft
from air.models.observation import AdsbObservation

CFG = SpoofingConfig()
T0 = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)

MIN_SAMPLES = CFG.altitude_quantum_min_samples
MAX_FT = CFG.altitude_quantum_max_ft


def track(altitudes: list[float | None], interval_s: float = 1.0):
    """One aircraft at the given altitudes, a second apart."""
    return [
        AdsbObservation(
            icao24="a1b2c3",
            observed_at=T0 + timedelta(seconds=i * interval_s),
            latitude=37.0,
            longitude=-79.0,
            altitude_ft=alt,
        )
        for i, alt in enumerate(altitudes)
    ]


def infer(altitudes, min_samples=MIN_SAMPLES, max_ft=MAX_FT):
    return infer_altitude_quantum_ft(track(altitudes), min_samples, max_ft)


def test_a_twenty_five_foot_reporter_is_read_as_twenty_five():
    assert infer([8000, 8025, 8050, 8075, 8100, 8125]) == 25.0


def test_a_hundred_foot_reporter_is_read_as_a_hundred():
    """The real case: FFL938, climbing honestly at ~1,500 fpm."""
    assert infer([8100, 8200, 8300, 8400, 8500, 8600]) == 100.0


def test_a_single_fine_step_settles_it_for_a_mixed_track():
    """Multiples of 100 do not prove a 100 ft reporter; one 25 disproves it."""
    assert infer([8000, 8100, 8200, 8300, 8325]) == 25.0


def test_level_flight_tells_us_nothing():
    """A level aircraft never shows its resolution, so we must not guess."""
    assert infer([8000, 8000, 8000, 8000, 8000, 8000]) is None


def test_too_few_changes_is_a_coincidence_not_a_measurement():
    """Two steps of 100 prove nothing about an aircraft that usually does 25."""
    assert infer([8000, 8100, 8200]) is None


def test_the_sample_floor_is_the_thing_being_enforced():
    """Same track, enough samples allowed: now it reads."""
    assert infer([8000, 8100, 8200], min_samples=2) == 100.0


def test_a_step_wider_than_the_ceiling_is_rejected():
    """Past the ceiling we are reading a climb, not a rounding step.

    Accepting it would hand the rule an allowance wide enough to hide a
    real lie, so the configured default applies instead.
    """
    assert infer([8000, 8500, 9000, 9500, 10000]) is None


def test_no_common_step_means_the_feed_is_not_rounding():
    assert infer([8000, 8033, 8071, 8114, 8160]) is None


def test_missing_altitudes_are_skipped_not_treated_as_zero():
    """A gap in reporting must not invent a step the aircraft never made."""
    assert infer([8000, None, 8025, 8050, None, 8075, 8100]) == 25.0


def test_direction_does_not_matter():
    """A descent rounds the same way a climb does."""
    assert infer([8125, 8100, 8075, 8050, 8025, 8000]) == 25.0


def test_an_empty_or_single_point_track_is_safe():
    assert infer([]) is None
    assert infer([8000]) is None


@pytest.mark.parametrize(
    "altitudes",
    [
        [8000, 8025, 8050, 8075, 8100],
        [8100, 8200, 8300, 8400, 8500],
        [8000, 8000, 8000],
        [],
    ],
)
def test_the_result_is_never_wider_than_the_ceiling(altitudes):
    result = infer(altitudes)
    assert result is None or 0 < result <= MAX_FT
