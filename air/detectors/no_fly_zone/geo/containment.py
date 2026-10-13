"""Stream C (part 2) - exact horizontal containment.

Decides whether the aircraft is inside a zone's polygon and how far inside.
Runs the strict point-in-polygon test *and* a buffered test that grows the
point by its position uncertainty: an aircraft reporting a poor NIC while
sitting 50 m outside the fence is not a confident clear.

Inputs
------
state:
    The observation to test.
zones:
    The short list from :func:`zone_index.candidate_zone_ids`. Passing the full
    set works but is slow.
cfg:
    Supplies ``geometry.default_uncertainty_m``, used when NIC/NACp are absent.

Outputs
-------
A :class:`ContainmentResult`. ``contained`` is the strict test,
``buffered_contained`` the uncertainty-aware one, ``penetration_nm`` the
distance inside the boundary (``None`` when outside), and ``zone_ids`` every
zone hit by either test.

Failure causes
--------------
ValueError
    A zone geometry is not a valid polygon.

Nothing hit is not an exception: the result carries
:attr:`ExitReason.OUTSIDE_POLYGON`, or :attr:`ExitReason.NO_CANDIDATE` when
``zones`` was empty. Never returns ``None``.

Notes
-----
DEVIATION from the CLAUDE.md signature table, which lists
``check_containment(state, zones)``. ``cfg`` is a required third argument
because ``default_uncertainty_m`` has to be passed in, never read inside a
module. Those two hard rules conflict; the lead should settle it.
"""
from __future__ import annotations

from collections.abc import Sequence

from ..config import Config
from ..types import AircraftState, AirspaceZone, ContainmentResult


def check_containment(
    state: AircraftState, zones: Sequence[AirspaceZone], cfg: Config
) -> ContainmentResult:
    """Test ``state`` against ``zones`` horizontally, strictly and buffered."""
    raise NotImplementedError("stream C: containment")
