"""Deduplication across sliding windows -- the ``dedup_scope`` contract.

``air.windowing.detection_dedup_key`` is what stops the same finding becoming
a new row every time the runner ticks. The detections table upserts on it, so
if the key moves, the upsert has nothing to match and the table grows without
bound.

Whether the time belongs in that key depends on what the finding *is*, and
only the detector knows, so the detector declares it in
``metadata["dedup_scope"]``. These tests pin both halves of that contract:
the generic behaviour in shared code, and spoofing's own choice of scope per
gate.

The bug this exists to prevent, measured on the Lynchburg capture at the live
3600 s / 300 s settings: 82 rows for 67 findings, the surplus being one
``nic_floor_v1`` written 5 times and ``identity_drift_v1`` written up to 8
times, each with a different key because its start slid with the window.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from air.detectors.spoofing.emit import _GATE_PHRASE, ENTITY_SCOPED_GATES
from air.windowing import (
    DEDUP_SCOPE_ENTITY,
    DEDUP_SCOPE_EVENT,
    detection_dedup_key,
)

T0 = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)


def _detection(*, start=T0, scope=None, entity="aircraft:a1b2c3", dtype="speed_delta"):
    """A duck-typed stand-in: the key only reads these attributes."""
    metadata = {"gate": "whatever"}
    if scope is not None:
        metadata["dedup_scope"] = scope
    return SimpleNamespace(
        detector_id="skywatch.spoofing",
        detector_version="0.1.0",
        detection_type=dtype,
        entities_involved=[SimpleNamespace(entity_id=entity)],
        temporal_bounds=SimpleNamespace(start_time=start),
        metadata=metadata,
    )


# --- the generic contract in shared code -------------------------------------
def test_an_event_scoped_finding_keeps_its_time_in_the_key():
    """Two disagreements about one aircraft at different times are two findings."""
    early = detection_dedup_key(_detection(start=T0, scope=DEDUP_SCOPE_EVENT))
    late = detection_dedup_key(
        _detection(start=T0 + timedelta(minutes=5), scope=DEDUP_SCOPE_EVENT)
    )
    assert early != late


def test_an_entity_scoped_finding_ignores_its_time():
    """The fix: a sliding start must not produce a new key every tick.

    This is the assertion the live bug would have failed.
    """
    early = detection_dedup_key(_detection(start=T0, scope=DEDUP_SCOPE_ENTITY))
    late = detection_dedup_key(
        _detection(start=T0 + timedelta(minutes=55), scope=DEDUP_SCOPE_ENTITY)
    )
    assert early == late


def test_entity_scope_still_separates_different_aircraft():
    """Collapsing on time must not collapse across entities.

    Without this, every aircraft with degraded integrity would share one row.
    """
    one = detection_dedup_key(_detection(entity="aircraft:a1b2c3", scope=DEDUP_SCOPE_ENTITY))
    two = detection_dedup_key(_detection(entity="aircraft:d4e5f6", scope=DEDUP_SCOPE_ENTITY))
    assert one != two


def test_entity_scope_still_separates_different_finding_types():
    """One aircraft can be in two bad states at once, and they are two rows."""
    nic = detection_dedup_key(_detection(dtype="integrity_degraded", scope=DEDUP_SCOPE_ENTITY))
    drift = detection_dedup_key(_detection(dtype="identity_drift", scope=DEDUP_SCOPE_ENTITY))
    assert nic != drift


def test_the_default_is_event_so_nothing_changes_for_a_detector_that_says_nothing():
    """Backwards compatibility, asserted rather than assumed.

    Proximity and No-Fly-Zone declare no scope, and this key is shared. If the
    default were ever flipped, their findings would start collapsing by
    entity and separate encounters would overwrite each other.
    """
    silent = _detection(scope=None)
    assert detection_dedup_key(silent) == detection_dedup_key(
        _detection(scope=DEDUP_SCOPE_EVENT)
    )
    # And it is genuinely time-sensitive, not merely equal by coincidence.
    assert detection_dedup_key(silent) != detection_dedup_key(
        _detection(start=T0 + timedelta(minutes=5), scope=None)
    )


def test_a_detection_with_no_metadata_at_all_still_works():
    """The key is used on anything Detection-shaped, including older fixtures."""
    bare = SimpleNamespace(
        detector_id="x",
        detector_version="1",
        detection_type="t",
        entities_involved=[SimpleNamespace(entity_id="e")],
        temporal_bounds=SimpleNamespace(start_time=T0),
    )
    assert isinstance(detection_dedup_key(bare), tuple)


def test_an_unrecognised_scope_raises_rather_than_guessing():
    """A typo must not silently disable deduplication.

    Falling back to either scope would hide the mistake: "event" reinstates the
    unbounded growth, "entity" collapses findings that should stay separate.
    Neither is detectable from the outside, so this fails loudly instead.
    """
    with pytest.raises(ValueError, match="unknown dedup_scope"):
        detection_dedup_key(_detection(scope="per-window"))


def test_the_key_is_deterministic():
    detection = _detection(scope=DEDUP_SCOPE_ENTITY)
    assert detection_dedup_key(detection) == detection_dedup_key(detection)


# --- spoofing's own choice of scope per gate ---------------------------------
def test_every_entity_scoped_gate_is_a_real_gate():
    """A typo here would silently leave a gate deduplicating on a sliding key."""
    unknown = ENTITY_SCOPED_GATES - set(_GATE_PHRASE)
    assert not unknown, f"not real gates: {sorted(unknown)}"


def test_the_gates_that_report_a_condition_are_entity_scoped():
    """These describe a state the aircraft is in, with no instant to anchor to.

    Each reports over whatever history the window held, so its start slides.
    """
    assert ENTITY_SCOPED_GATES == {
        "nic_floor_v1",
        "coexistence_v1",
        "pingpong_v1",
        "identity_drift_v1",
    }


@pytest.mark.parametrize(
    "gate",
    ["speed_delta_v1", "turn_rate_v1", "vrate_delta_v1", "subterrain_v1", "teleport_v1"],
)
def test_pair_anchored_gates_stay_event_scoped(gate):
    """They fire on two specific reports, whose timestamps do not move.

    So they need no special handling, and two of them about one aircraft at
    different times must stay two findings.
    """
    assert gate not in ENTITY_SCOPED_GATES


def test_reappear_is_event_scoped_because_it_anchors_to_its_gap():
    """Not an oversight -- an aircraft can reappear impossibly more than once.

    Entity-scoping it would collapse two separate reappearances into one. It
    is handled instead by anchoring its bounds to the two reports either side
    of the gap, in air/detectors/spoofing/detector.py.
    """
    assert "reappear_v1" not in ENTITY_SCOPED_GATES
