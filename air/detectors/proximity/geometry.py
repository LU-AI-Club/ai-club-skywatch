"""Pure geometry for aircraft pairs: distance, local coordinates, closest approach.

Everything here is plain math on floats. No pandas, no objects, no state. Each
function is small enough to check by hand against the fixtures.

Units, fixed once here:
    positions   -> degrees in, METRES out (local x/y)
    speeds      -> knots in, METRES PER SECOND out
    horizontal  -> nautical miles when reported to a human
    vertical    -> feet, always
    time        -> seconds

OWNER: Manni (to_local_xy, velocity_xy, time_to_cpa, predicted_separation).
       haversine_nm is done — use it as the model for the rest.
"""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_000.0
M_PER_NM = 1852.0
KT_TO_MPS = M_PER_NM / 3600.0  # 1 knot = 1 nm/h = 1852 m / 3600 s


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in nautical miles.

    DONE — the worked example. Notice: degrees -> radians first, and the
    answer is converted to nm at the very end.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a)) / M_PER_NM


def to_local_xy(lat: float, lon: float, ref_lat: float, ref_lon: float) -> tuple[float, float]:
    """Project a lat/lon onto a flat local plane centred on (ref_lat, ref_lon).

    Returns ``(x_m, y_m)``: metres EAST and metres NORTH of the reference.
    Within ~50 nm the earth is flat enough that this "equirectangular"
    projection is accurate to a few metres, which is all we need.

        x = R * radians(lon - ref_lon) * cos(radians(ref_lat))
        y = R * radians(lat - ref_lat)

    The cos() term is the whole trick: a degree of longitude shrinks as you go
    north. Forget it and every east-west distance is ~20% too big at Lynchburg.
    """
    x_m = EARTH_RADIUS_M * math.radians(lon - ref_lon) * math.cos(math.radians(ref_lat))
    y_m = EARTH_RADIUS_M * math.radians(lat - ref_lat)
    return x_m, y_m


def velocity_xy(ground_speed_kt: float, track_deg: float) -> tuple[float, float]:
    """Split a speed + compass track into ``(vx, vy)`` in metres per second.

    Compass convention: 0 deg = north, 90 deg = east, clockwise. So

        vx (east)  = speed * sin(track)
        vy (north) = speed * cos(track)

    Note that is sin for x and cos for y — the opposite of maths-class angles,
    because compass angles start at north and go clockwise.
    """
    speed_mps = ground_speed_kt * KT_TO_MPS
    heading_rad = math.radians(track_deg)
    return speed_mps * math.sin(heading_rad), speed_mps * math.cos(heading_rad)


def time_to_cpa(rx: float, ry: float, vx: float, vy: float) -> float | None:
    """Seconds until two aircraft are closest, assuming both fly straight.

    ``(rx, ry)`` is B's position relative to A in metres; ``(vx, vy)`` is B's
    velocity relative to A in m/s. The formula:

        t_cpa = -(r . v) / |v|^2

    Sign matters:
        t_cpa > 0  -> still closing, closest point is in the future
        t_cpa < 0  -> already past closest point, diverging
        t_cpa = 0  -> closest right now

    Return ``None`` when |v| is (near) zero — same speed and heading means the
    separation never changes and there is no closest approach to speak of.
    """
    speed_sq = vx * vx + vy * vy
    if speed_sq < 1e-18:  # Relative speed below 1 nanometre per second.
        return None
    return -(rx * vx + ry * vy) / speed_sq


def predicted_separation(
    rx: float,
    ry: float,
    vx: float,
    vy: float,
    t_s: float,
    vertical_now_ft: float,
    vertical_rate_diff_fpm: float,
) -> tuple[float, float]:
    """Horizontal (nm) and vertical (ft) separation ``t_s`` seconds from now.

    Straight-line extrapolation of the relative state:

        horizontal_m = | r + v * t |
        vertical_ft  = | vertical_now_ft + vertical_rate_diff_fpm * t / 60 |

    ``vertical_rate_diff_fpm`` is (B's climb rate - A's climb rate) in ft/min,
    signed the same way as ``vertical_now_ft`` (B's altitude - A's altitude).
    Return absolute values — separation is a distance, never negative.
    """
    horizontal_nm = math.hypot(rx + vx * t_s, ry + vy * t_s) / M_PER_NM
    vertical_ft = abs(vertical_now_ft + vertical_rate_diff_fpm * t_s / 60.0)
    return horizontal_nm, vertical_ft


__all__ = [
    "EARTH_RADIUS_M",
    "KT_TO_MPS",
    "M_PER_NM",
    "haversine_nm",
    "predicted_separation",
    "time_to_cpa",
    "to_local_xy",
    "velocity_xy",
]
