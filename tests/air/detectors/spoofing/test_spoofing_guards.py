"""The floor: misbehaviour the detector must catch at any threshold.

Every other fixture asks whether a rule works. These ask whether the detector
is still worth running. They are gross, unambiguous cases -- 300 nm in ten
seconds, a 390 kt speed lie measured over half a minute -- chosen so that no
defensible loosening of a threshold could reach them.

That makes them the safety net for calibration. We are deliberately tuning
alerts down, and the honest failure mode of that work is tuning until nothing
fires at all. If a change turns one of these green, the change went too far,
whatever the alert count says. Fix the threshold, not the fixture.

Each guard is asserted twice: that something fired, and that the rule which
fired is the one the scenario was built for. Only the first would pass if a
single over-eager rule started flagging everything.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from air.detectors.spoofing.detector import SpoofingDetector

FIXTURES_DIR = (
    Path(__file__).resolve().parents[4] / "air" / "fixtures" / "spoofing"
)

# fixture -> the gate whose absence means we have tuned past the floor.
GUARDS = {
    "pos_guard_teleport.json": "teleport_v1",
    "pos_guard_turn_at_cruise.json": "turn_rate_v1",
    "pos_guard_speed_lie_long_gap.json": "speed_delta_v1",
    "pos_guard_vrate_lie_at_cruise.json": "vrate_delta_v1",
    "pos_guard_integrity_collapse.json": "nic_floor_v1",
    "pos_guard_impersonation.json": "coexistence_v1",
}


def test_every_guard_fixture_on_disk_is_covered():
    """A new pos_guard_* file that no test names is a guard in name only."""
    on_disk = {p.name for p in FIXTURES_DIR.glob("pos_guard_*.json")}
    assert on_disk == set(GUARDS), (
        "pos_guard_* fixtures and GUARDS disagree; "
        "regenerate the fixtures or add the new one to GUARDS"
    )


@pytest.mark.parametrize("fixture", sorted(GUARDS))
def test_guard_fixture_still_produces_a_detection(fixture, observations_from):
    """Something must fire. Silence here means the detector has gone blind."""
    detections = SpoofingDetector().detect_observations(
        observations_from(f"spoofing/{fixture}")
    )
    assert detections, (
        f"{fixture} produced no detection at all -- a threshold has been "
        f"loosened past the point where the detector is useful"
    )


@pytest.mark.parametrize("fixture,gate", sorted(GUARDS.items()))
def test_guard_fixture_fires_the_rule_it_was_built_for(
    fixture, gate, observations_from
):
    """The right rule must fire, not merely some rule."""
    detections = SpoofingDetector().detect_observations(
        observations_from(f"spoofing/{fixture}")
    )
    fired = {d.metadata["gate"] for d in detections}
    assert gate in fired, f"{fixture}: expected {gate}, got {sorted(fired)}"


@pytest.mark.parametrize("fixture,gate", sorted(GUARDS.items()))
def test_guard_fixtures_are_labelled_positive_for_the_harness(fixture, gate):
    """run_on_fixtures reads _label, not the filename.

    A guard labelled anything but ``positive:<gate>`` is scored as a negative
    by the evaluation harness, so a sweep that silenced it would read as an
    improvement. The pos_guard_ filename is what marks it as a guard; the
    label is what makes it count.
    """
    rows = json.loads((FIXTURES_DIR / fixture).read_text(encoding="utf-8"))
    assert rows, fixture
    assert all(row["_label"] == f"positive:{gate}" for row in rows), fixture
