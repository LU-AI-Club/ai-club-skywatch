"""Stream G - score, severity, and the Detection contract.

Turns the upstream stage results into one :class:`Detection`. This is the only
module that decides how bad something is, so the whole policy is readable in
one place.

Scoring shape
-------------
Start from ``scoring.base_by_zone_type[zone.zone_type]``. Add a depth bump of
``scoring.depth_bump_per_nm`` per nautical mile of penetration, capped at
``scoring.depth_bump_max``. Subtract the weight of every
:class:`ContextSignal`. Clamp the result to ``[0.0, 1.0]``.

Severity caps
-------------
``activation.state is UNKNOWN``
    Cap at ``severity.unknown_activation_cap`` - we never treat a maybe-cold
    zone as a confirmed incursion.
``containment.contained is False`` but ``buffered_contained is True``
    Cap at ``severity.buffered_only`` - this may be position error, not a
    violation.

Inputs
------
state, zone, containment, vertical, activation, signals, cfg:
    The outputs of streams A-F plus config.

Outputs
-------
One :class:`Detection`. ``baseline_or_model_version`` must come from
:meth:`Config.baseline_version`, which pins both the rules version and the
airspace publication cycle. ``explanation_facts`` must be reconstructable from
the inputs, and ``limitations`` must state what the detector could not check
(unknown activation, barometric-only altitude, AGL floor not evaluated).

Required ``extras`` keys
------------------------
``emit.to_platform_detection`` converts this Detection into the vendored
SENTINEL contract, which requires a timestamp and provenance that
``types.Detection`` does not carry. Put them in ``extras`` or emitting fails:

``observed_at``     the AircraftState timestamp (tz-aware UTC)
``source_row_id``   provenance back to the raw record
``lat`` / ``lon``   position, for the geospatial centroid

Also populate ``altitude_ft``, ``zone_id`` and ``penetration_nm`` when known -
they become the platform record's geospatial context.

Failure causes
--------------
KeyError
    ``zone.zone_type`` has no entry in ``scoring.base_by_zone_type``. Config
    validation already guards this, so reaching it means config drifted.
ValueError
    The computed score falls outside ``[0.0, 1.0]`` before clamping, which
    means a weight is misconfigured.

Notes
-----
No constants inline. Every number above comes from ``cfg``.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..types import (
    ActivationResult,
    AircraftState,
    AirspaceZone,
    ContainmentResult,
    ContextSignal,
    Detection,
    VerticalResult,
)


def build_detection(
    state: AircraftState,
    zone: AirspaceZone,
    containment: ContainmentResult,
    vertical: VerticalResult,
    activation: ActivationResult,
    signals: Sequence[ContextSignal],
    cfg: Config,
) -> Detection:
    """Score one confirmed incursion and emit the Detection contract."""
    raise NotImplementedError("stream G: scoring")
