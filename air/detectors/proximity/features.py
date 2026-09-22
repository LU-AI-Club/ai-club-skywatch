"""The feature record: what the rules get to look at for one pair.

``PairGeometry`` is the contract between the math (geometry.py) and the
rulebook (rules.py). The math fills it in; the rules only ever read it. Freezing
this shape is what let both halves be built at the same time.

Already done — nobody needs to edit this file to finish the MVP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from air.detectors.proximity.geometry import (
    haversine_nm,
    predicted_separation,
    time_to_cpa,
    to_local_xy,
    velocity_xy,
)
from air.models.observation import AdsbObservation


@dataclass(frozen=True, slots=True)
class PairGeometry:
    """Everything the rules need to know about one pair at one instant."""

    icao_a: str
    icao_b: str
    at: datetime
    horizontal_now_nm: float
    vertical_now_ft: float
    closure_rate_kt: float          # + means closing, - means opening
    t_cpa_s: float | None           # None when relative velocity is ~0
    predicted_horizontal_nm: float | None
    predicted_vertical_ft: float | None
    obs_a: AdsbObservation
    obs_b: AdsbObservation

    @property
    def converging(self) -> bool:
        return self.t_cpa_s is not None and self.t_cpa_s > 0


# --- Features (done; pure glue over geometry.py) ------------------------------
def pair_geometry(a: AdsbObservation, b: AdsbObservation) -> PairGeometry | None:
    """DONE. Relative state of the pair, or None if a needed field is missing."""
    if None in (a.altitude_ft, b.altitude_ft, a.ground_speed_kt, b.ground_speed_kt, a.track_deg, b.track_deg):
        return None
    assert a.altitude_ft is not None and b.altitude_ft is not None
    # Local plane centred on A, so A sits at the origin.
    bx, by = to_local_xy(b.latitude, b.longitude, a.latitude, a.longitude)
    avx, avy = velocity_xy(a.ground_speed_kt, a.track_deg)  # type: ignore[arg-type]
    bvx, bvy = velocity_xy(b.ground_speed_kt, b.track_deg)  # type: ignore[arg-type]
    rx, ry = bx, by
    vx, vy = bvx - avx, bvy - avy

    vertical_now = b.altitude_ft - a.altitude_ft
    vrate_diff = (b.vertical_rate_fpm or 0.0) - (a.vertical_rate_fpm or 0.0)
    dist_m = (rx * rx + ry * ry) ** 0.5
    # Closure rate = -(rate of change of distance) = -(r . v)/|r|, in knots.
    closure_mps = 0.0 if dist_m < 1e-6 else -(rx * vx + ry * vy) / dist_m
    closure_kt = closure_mps * 3600.0 / 1852.0

    t = time_to_cpa(rx, ry, vx, vy)
    if t is None:
        pred_h, pred_v = None, None
    else:
        pred_h, pred_v = predicted_separation(rx, ry, vx, vy, t, vertical_now, vrate_diff)

    return PairGeometry(
        icao_a=a.icao24,
        icao_b=b.icao24,
        at=a.observed_at,
        horizontal_now_nm=haversine_nm(a.latitude, a.longitude, b.latitude, b.longitude),
        vertical_now_ft=abs(vertical_now),
        closure_rate_kt=closure_kt,
        t_cpa_s=t,
        predicted_horizontal_nm=pred_h,
        predicted_vertical_ft=pred_v,
        obs_a=a,
        obs_b=b,
    )


__all__ = ["PairGeometry", "pair_geometry"]
