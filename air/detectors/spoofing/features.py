"""Feature calculations for ADS-B spoofing detection.

Turns a stream of observations into the records every rule tests:

    group_by_aircraft   -> one time-ordered track per aircraft
    split_segments      -> unbroken stretches, split where the aircraft went quiet
    build_pair_features -> one record per consecutive pair inside a segment
    build_features      -> all of the above, over every aircraft

A single observation can never be wrong -- there is nothing to contradict it.
Every number here comes from comparing one report with the one before it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable, Sequence

from air.detectors.spoofing.records import SpoofingFeatureRecord
from air.models.observation import AdsbObservation

EARTH_RADIUS_M = 6_371_000.0

# Unit conversions, fixed here so no caller re-derives them.
MPS_TO_KT = 1.943844
DEFAULT_MAX_GAP_S = 60.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance between two degree coordinates in metres."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    delta_lat = p2 - p1
    delta_lon = math.radians(lon2 - lon1)
    haversine = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(haversine))


def heading_delta_deg(from_deg: float, to_deg: float) -> float:
    """Return the signed turn between two headings, in degrees.

    The result sits in [-180, 180): negative is a left turn, positive a right
    turn. Headings wrap, so 359 to 1 is +2 degrees, not -358. Without that
    wrap, every aircraft flying north looks like it is spinning.

    An exact reversal comes back as -180 rather than +180. Which way an
    aircraft turned through a half circle is genuinely ambiguous, and the
    rules compare magnitudes, so the sign there carries no meaning.
    """
    return (float(to_deg) - float(from_deg) + 180.0) % 360.0 - 180.0


def group_by_aircraft(
    observations: Iterable[AdsbObservation],
) -> dict[str, list[AdsbObservation]]:
    """Sort a mixed stream into one time-ordered track per aircraft.

    Reports from every aircraft arrive interleaved, and each rule needs one
    aircraft's reports in the order they happened.

    Sorting is by ``observed_at``, never by position in the input: messages do
    arrive out of order, and a track in arrival order would invent impossible
    movement that no aircraft performed.
    """
    tracks: dict[str, list[AdsbObservation]] = defaultdict(list)
    for observation in observations:
        tracks[observation.icao24].append(observation)
    for track in tracks.values():
        track.sort(key=lambda obs: obs.observed_at)
    return dict(tracks)


def split_segments(
    track: Sequence[AdsbObservation], max_gap_s: float = DEFAULT_MAX_GAP_S
) -> list[list[AdsbObservation]]:
    """Break one aircraft's track wherever it went quiet for too long.

    Aircraft fall silent constantly and almost always innocently: out of
    receiver range, behind terrain, powered down on a ramp, or shadowing their
    own belly antenna through a turn. Measuring speed across a ten-minute
    silence produces a number that means nothing, because we have no idea what
    happened in between.

    So wherever the gap exceeds ``max_gap_s`` a new segment starts, and no
    feature is ever computed across that boundary. The one question worth
    asking about a gap -- could the aircraft have reached where it reappeared?
    -- belongs to ``flag_reappearance``, not here.
    """
    if not track:
        return []

    ordered = sorted(track, key=lambda obs: obs.observed_at)
    segments: list[list[AdsbObservation]] = [[ordered[0]]]
    for previous, current in zip(ordered, ordered[1:]):
        gap_s = (current.observed_at - previous.observed_at).total_seconds()
        if gap_s > max_gap_s:
            segments.append([current])
        else:
            segments[-1].append(current)
    return segments


def build_pair_features(
    previous: AdsbObservation,
    current: AdsbObservation,
    segment_id: int = 0,
) -> SpoofingFeatureRecord | None:
    """Work out what one consecutive pair of reports implies.

    This is where the detector's arithmetic happens. Two reports give the time
    between them and the distance moved, and therefore the speed the aircraft
    *must* have been doing -- which is then compared against the speed it
    *claimed*. Same for climb rate and turn rate.

    Returns ``None`` when the pair cannot be used: a non-positive time gap,
    meaning the reports arrived out of order, or two different aircraft.
    Dividing by a zero gap would imply infinite speed, so the pair is dropped
    rather than scored.
    """
    if previous.icao24 != current.icao24:
        return None

    dt_s = (current.observed_at - previous.observed_at).total_seconds()
    if dt_s <= 0:
        return None

    dist_m = haversine_m(
        previous.latitude, previous.longitude, current.latitude, current.longitude
    )
    implied_speed_kt = (dist_m / dt_s) * MPS_TO_KT

    reported_speed_kt = current.ground_speed_kt
    speed_delta_kt = (
        None if reported_speed_kt is None else implied_speed_kt - reported_speed_kt
    )

    implied_vrate_fpm = None
    if previous.altitude_ft is not None and current.altitude_ft is not None:
        implied_vrate_fpm = (current.altitude_ft - previous.altitude_ft) / (dt_s / 60.0)

    reported_vrate_fpm = current.vertical_rate_fpm
    vrate_delta_fpm = (
        None
        if implied_vrate_fpm is None or reported_vrate_fpm is None
        else implied_vrate_fpm - reported_vrate_fpm
    )

    turn_rate_dps = None
    if previous.track_deg is not None and current.track_deg is not None:
        turn_rate_dps = heading_delta_deg(previous.track_deg, current.track_deg) / dt_s

    return SpoofingFeatureRecord(
        icao24=current.icao24,
        segment_id=segment_id,
        prev_observed_at=previous.observed_at,
        curr_observed_at=current.observed_at,
        dt_s=dt_s,
        dist_m=dist_m,
        implied_speed_kt=implied_speed_kt,
        reported_speed_kt=reported_speed_kt,
        speed_delta_kt=speed_delta_kt,
        implied_vrate_fpm=implied_vrate_fpm,
        reported_vrate_fpm=reported_vrate_fpm,
        vrate_delta_fpm=vrate_delta_fpm,
        turn_rate_dps=turn_rate_dps,
        prev_latitude=previous.latitude,
        prev_longitude=previous.longitude,
        curr_latitude=current.latitude,
        curr_longitude=current.longitude,
        altitude_ft=current.altitude_ft,
        nic=current.nic,
        nacp=current.nacp,
        prev_nic=previous.nic,
        prev_nacp=previous.nacp,
        callsign=current.callsign,
    )


def build_features(
    observations: Iterable[AdsbObservation], max_gap_s: float = DEFAULT_MAX_GAP_S
) -> list[SpoofingFeatureRecord]:
    """Run the whole calculation stage over every aircraft.

    Group by aircraft, split each track on gaps, then build one record per
    consecutive pair *inside* a segment. Pairs spanning a gap are never built,
    which is the entire point of segmenting first.

    ``segment_id`` counts from 0 per aircraft, so a rule can tell whether two
    records belong to the same unbroken stretch of flight.
    """
    records: list[SpoofingFeatureRecord] = []
    for track in group_by_aircraft(observations).values():
        for segment_id, segment in enumerate(split_segments(track, max_gap_s)):
            for previous, current in zip(segment, segment[1:]):
                record = build_pair_features(previous, current, segment_id)
                if record is not None:
                    records.append(record)
    return records


__all__ = [
    "haversine_m",
    "heading_delta_deg",
    "group_by_aircraft",
    "split_segments",
    "build_pair_features",
    "build_features",
    "EARTH_RADIUS_M",
    "MPS_TO_KT",
    "DEFAULT_MAX_GAP_S",
]
