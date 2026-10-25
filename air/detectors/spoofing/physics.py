"""Physics rules: could the aircraft have moved this way?

Each rule takes a feature record and the config, and returns a short reason
string when it fires or ``None`` when it does not. That shape comes from
``flag_altitude`` in the reference detector.

These limits sit beyond what is physically possible, so a hit here is a
finding rather than a judgement call. The identity rules in ``identity.py``
answer the other question: is this the aircraft it claims to be?

Missing input always means ``None``. A rule that guesses at absent data
invents detections, and the repo rule is to abstain instead.
"""

from __future__ import annotations

from typing import Sequence

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.features import MPS_TO_KT
from air.detectors.spoofing.records import SpoofingFeatureRecord
from air.models.observation import AdsbObservation

# NACp -> 95% horizontal position error bound (EPU), in metres.
# Source: DO-260B table of NACp values -- verify against the spec before citing.
# NACp 0 means "unknown" and is deliberately absent, so it contributes no
# allowance (behaviour is unchanged when the feed does not say how good the
# fix was).
NACP_EPU_M: dict[int, float] = {
    11: 3.0,
    10: 10.0,
    9: 30.0,
    8: 93.0,
    7: 185.0,
    6: 556.0,
    5: 926.0,
    4: 1852.0,
    3: 3704.0,
    2: 7408.0,
    1: 18520.0,
}


def position_error_speed_kt(record: SpoofingFeatureRecord) -> float:
    """Implied speed that position error alone can produce over this gap.

    A jump is a claim about two positions, and either can be off by its own
    error bound, so the two bounds add. Dividing by a short gap turns a small
    position error into a large phantom speed, the same way altitude
    quantisation does for climb rate.

    Missing or zero NACp (unknown) contributes nothing. A self-reported low
    NACp therefore only buys slack equal to the error radius it claims; it
    does not make a gross teleport invisible.
    """
    err_m = sum(
        NACP_EPU_M.get(nacp, 0.0)
        for nacp in (record.prev_nacp, record.nacp)
        if nacp
    )
    return err_m / record.dt_s * MPS_TO_KT


def flag_teleport(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> str | None:
    """Flag movement faster than any aircraft can manage over the ground.

    The threshold is deliberately far above real flight. Airliners reach
    750-800 kt with a strong tailwind, so a limit near cruise speed would
    flag honest traffic all day; a fabricated position typically implies
    thousands of knots, so nothing real is lost by setting it at 1000.

    The implied speed is first reduced by what the reports' own position
    error could explain, so a poor fix is not mistaken for a fabricated one.
    """
    if record.implied_speed_kt is None:
        return None
    if record.dt_s < cfg.min_dt_s:
        # Timestamp error dominates at very short gaps.
        return None
    if record.implied_speed_kt - position_error_speed_kt(record) > cfg.teleport_kt:
        return "TELEPORT"
    return None


def flag_turn_rate(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> str | None:
    """Flag a turn sharper than an airframe can fly.

    Turn rate is signed in the record -- negative is a left turn -- so the
    comparison uses its magnitude. A standard rate turn is 3 deg/s.

    Track comes from the velocity message, not the position fix, so NIC/NACp
    deliberately play no part here.
    """
    if record.turn_rate_dps is None:
        return None
    if record.dt_s < cfg.min_dt_s:
        return None
    if abs(record.turn_rate_dps) > cfg.turn_rate_dps:
        return "IMPOSSIBLE_TURN"
    return None


def speed_delta_limit_kt(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> float | None:
    """The effective speed-disagreement limit for this record.

    The larger of the fixed margin and a fraction of the reported speed, so
    the rule works for a 90 kt trainer and a 500 kt jet alike, plus the
    phantom speed position error alone can produce over this gap. Exposed
    because the event records the limit that actually applied, not the
    config constant.
    """
    if record.reported_speed_kt is None:
        return None
    base = max(cfg.speed_delta_kt, abs(record.reported_speed_kt) * cfg.speed_delta_frac)
    return base + speed_position_error_kt(record, cfg)


def speed_position_error_kt(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> float:
    """How much apparent speed position error alone can produce.

    Either endpoint can be off by the position error, so the distance can be
    wrong by up to twice that, and dividing by a short gap produces a large
    phantom speed:

        2 x 30 m over 0.55 s  ->  212 kt, on an aircraft flying steadily

    This returns that bound so the rule can allow for it. It shrinks as the
    gap grows -- 23 kt at 5 s, 4 kt at 30 s -- so a real contradiction over a
    longer gap is still caught at nearly the original limit.
    """
    if record.dt_s <= 0:
        return float("inf")
    return 2.0 * cfg.position_error_m / record.dt_s * MPS_TO_KT


def flag_speed_delta(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> str | None:
    """Flag a claimed ground speed that contradicts the aircraft's own positions.

    Aircraft broadcast velocity separately from position. When the two
    disagree by more than wind and sensor error explain, at least one of them
    is fabricated.

    Implied speed comes from the two positions, so the disagreement is first
    reduced by what position error alone could produce (see
    ``position_error_speed_kt``). Only the remainder is compared to the limit.
    """
    if record.speed_delta_kt is None:
        return None
    if record.dt_s < cfg.min_dt_s:
        return None
    limit = speed_delta_limit_kt(record, cfg)
    if limit is None:
        return None
    disagreement = abs(record.speed_delta_kt) - position_error_speed_kt(record)
    if disagreement > limit:
        return "SPEED_DISAGREEMENT"
    return None


def vrate_quantisation_fpm(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> float:
    """How much apparent climb rate the altitude step size alone can produce.

    Altitude is reported in fixed steps -- 25 ft in this feed -- so a level
    aircraft still appears to jump a whole step at a time. Either endpoint
    can be rounded, so the error is up to two steps, and dividing that by a
    short gap produces a large phantom rate:

        25 ft over 0.55 s  ->  2,727 fpm, on an aircraft flying level

    This returns that bound so the rule can ignore it. It shrinks as the gap
    grows, which is why a longer gap is more trustworthy here.
    """
    if record.dt_s <= 0:
        return float("inf")
    return 2.0 * cfg.altitude_quantum_ft * 60.0 / record.dt_s


def flag_vrate_delta(
    record: SpoofingFeatureRecord, cfg: SpoofingConfig
) -> str | None:
    """Flag a claimed climb rate that contradicts the altitude change.

    Same idea as the speed check, one axis up: the aircraft reports a
    vertical rate, and its own altitudes imply another. A large disagreement
    means one of the two is invented.

    The comparison allows for altitude quantisation first. Without that, this
    rule produced 16,953 of 17,733 alerts on one hour of real data, nearly
    all of them level aircraft observed half a second apart. Subtracting the
    step-size artefact is the honest fix: widening the threshold instead
    would have hidden real disagreements at long gaps.
    """
    if record.vrate_delta_fpm is None:
        return None
    if record.dt_s < cfg.min_dt_s:
        return None

    disagreement = abs(record.vrate_delta_fpm) - vrate_quantisation_fpm(record, cfg)
    if disagreement > cfg.vrate_delta_fpm:
        return "VRATE_DISAGREEMENT"
    return None


def flag_nic_floor(
    segment: Sequence[AdsbObservation], cfg: SpoofingConfig
) -> str | None:
    """Flag navigation integrity that stays on the floor.

    Aircraft report how far they trust their own position fix. Under GNSS
    jamming that value collapses and stays down, which is the clearest
    single sign of interference available to us.

    The duration matters as much as the value: brief dips are ordinary
    equipment behaviour, so the run must last at least
    ``cfg.nic_min_duration_s``. This is the one rule that reads a whole
    segment rather than a pair, because a single report cannot show duration.

    Note this will never fire on ``data/lynchburg_adsb.csv`` -- nothing in
    that hour drops below NIC 5. Test it against
    ``air/fixtures/spoofing/pos_integrity_collapse.json``.
    """
    if len(segment) < 2:
        return None

    run_start = None
    for observation in segment:
        if observation.nic is not None and observation.nic <= cfg.nic_floor:
            if run_start is None:
                run_start = observation.observed_at
                continue
            held_s = (observation.observed_at - run_start).total_seconds()
            if held_s >= cfg.nic_min_duration_s:
                return "INTEGRITY_FLOOR"
        else:
            run_start = None
    return None


def flag_subterrain(
    record: SpoofingFeatureRecord,
    terrain_elevation_ft: float | None,
    cfg: SpoofingConfig,
) -> str | None:
    """Flag an aircraft reporting a position below the ground beneath it.

    The hardest impossibility in the detector: an aircraft cannot be inside
    terrain. Either the altitude or the position is false.

    ``terrain_elevation_ft`` comes from an elevation dataset (SRTM or USGS)
    looked up at the reported position. When no elevation is available --
    outside coverage, or over water -- this abstains rather than assuming
    sea level, because assuming would flag every aircraft on approach to a
    high-altitude airport.
    """
    if terrain_elevation_ft is None or record.altitude_ft is None:
        return None
    if record.altitude_ft < terrain_elevation_ft:
        return "BELOW_TERRAIN"
    return None


def subterrain_depth_ft(
    record: SpoofingFeatureRecord, terrain_elevation_ft: float | None
) -> float | None:
    """How far below the ground the aircraft claims to be, as a positive number.

    Events store ``measured`` as a positive value, so depth is reported
    rather than a negative height: 300.0 means 300 ft underground.
    """
    if terrain_elevation_ft is None or record.altitude_ft is None:
        return None
    depth = terrain_elevation_ft - record.altitude_ft
    return depth if depth > 0 else None


__all__ = [
    "flag_teleport",
    "flag_turn_rate",
    "flag_speed_delta",
    "flag_vrate_delta",
    "flag_nic_floor",
    "flag_subterrain",
    "speed_delta_limit_kt",
    "speed_position_error_kt",
    "subterrain_depth_ft",
    "position_error_speed_kt",
    "NACP_EPU_M",
]