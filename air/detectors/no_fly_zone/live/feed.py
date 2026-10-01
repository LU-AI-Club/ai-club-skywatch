"""Map one Flys Down aircraft response into :class:`AircraftState` records.

Inputs
------
payload:
    Parsed JSON from ``GET /api/aircraft``. Shape, confirmed against
    flysdown's shared/adsb.js and functions/api/aircraft.js::

        {ok, source, via, fetchedAt (epoch ms), ageMs?, stale?, coverage,
         count, aircraft: [{id, callsign, lat, lon, alt, altGeom, onGround,
         groundSpeed, track, squawk, category, seen, seenPos, source, ...}]}

received_at:
    When this process received the response (tz-aware UTC).
live_cfg:
    The ``feed`` section of config/live_flysdown.yaml.

Timing, stated plainly
----------------------
The feed has no per-aircraft observation time. It has ``fetchedAt``, when the
snapshot was stored (relay path) or fetched (edge path), and ``seenPos``, how
many seconds old each position was when the upstream answered. So the
observation time used here is an **estimate**, ``fetchedAt - seenPos``. It is
later than the truth by the relay's unmeasured fetch-to-store delay (usually a
second or two), which makes positions look slightly fresher than they are.
Every state records that basis, and every detection carries it as a
limitation. A record with no ``seenPos`` cannot be timed at all and is
skipped, never stamped with the fetch time.

Altitude
--------
``alt`` is barometric, falling back to geometric upstream when barometric is
missing; ``altGeom`` is geometric. Stream D prefers geometric, so ``alt`` is
only ever compared when ``altGeom`` is missing, and then it is barometric.

The feed carries neither NIC nor NACp, so both are ``None`` and stream C uses
the configured default uncertainty.

Outputs
-------
A :class:`FeedBatch`: the feed's status, the usable states, per-state timing
keyed by ``source_row_id``, and counts of what was skipped and why.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Any

from ..types import AircraftState

FRESH = "fresh"
STALE = "stale"
UNAVAILABLE = "unavailable"

TIMESTAMP_BASIS = "estimated: feed fetchedAt minus seenPos"
_EARTH_RADIUS_NM = 3440.065


@dataclass(frozen=True, slots=True)
class FeedStatus:
    status: str                      # fresh | stale | unavailable
    reason: str | None
    source: str | None               # e.g. "relay/adsb.fi"
    via: str | None                  # relay | edge
    fetched_at: datetime | None
    snapshot_age_s: float | None     # received_at - fetchedAt, our clock
    server_age_ms: float | None      # the feed's own ageMs, when it sent one
    count: int


@dataclass(frozen=True, slots=True)
class StateTiming:
    observed_at: datetime
    basis: str
    seen_pos_s: float
    position_age_s: float            # at received_at


@dataclass(frozen=True, slots=True)
class FeedBatch:
    status: FeedStatus
    states: tuple[AircraftState, ...] = ()
    timing: Mapping[str, StateTiming] = field(default_factory=dict)
    skipped: Mapping[str, int] = field(default_factory=dict)


def map_feed(
    payload: Any,
    received_at: datetime,
    live_cfg: Mapping[str, Any],
    scope: Mapping[str, Any] | None = None,
) -> FeedBatch:
    """Turn one response into states, or into a status saying why not.

    A stale or unavailable feed returns no states at all, so a quiet result
    from it can never be mistaken for "evaluated and nothing found".

    Raises:
        ValueError: ``received_at`` is naive.
    """
    if received_at.tzinfo is None:
        raise ValueError("received_at must be tz-aware UTC")

    if not isinstance(payload, Mapping):
        return FeedBatch(_status(UNAVAILABLE, "response was not a JSON object"))
    if payload.get("ok") is not True:
        detail = payload.get("error") or "feed reported ok=false"
        return FeedBatch(_status(UNAVAILABLE, str(detail)[:200], payload))
    aircraft = payload.get("aircraft")
    fetched_ms = payload.get("fetchedAt")
    if not isinstance(aircraft, list):
        return FeedBatch(_status(UNAVAILABLE, "response had no aircraft list", payload))
    if not isinstance(fetched_ms, (int, float)) or isinstance(fetched_ms, bool):
        return FeedBatch(_status(UNAVAILABLE, "response had no fetchedAt time", payload))

    fetched_at = datetime.fromtimestamp(fetched_ms / 1000, tz=UTC)
    age_s = (received_at - fetched_at).total_seconds()
    max_age = float(live_cfg["max_snapshot_age_s"])
    if payload.get("stale") is True:
        reason = "the feed marked this snapshot stale"
        return FeedBatch(_status(STALE, reason, payload, fetched_at, age_s))
    if age_s > max_age:
        reason = f"snapshot is {age_s:.0f}s old (limit {max_age:.0f}s)"
        return FeedBatch(_status(STALE, reason, payload, fetched_at, age_s))

    source = str(payload.get("source") or "unknown")
    max_position_age = float(live_cfg["max_position_age_s"])
    skipped: Counter[str] = Counter()
    states: list[AircraftState] = []
    timing: dict[str, StateTiming] = {}
    for raw in aircraft:
        if not isinstance(raw, Mapping):
            skipped["malformed_record"] += 1
            continue
        lat, lon, ident = _num(raw.get("lat")), _num(raw.get("lon")), raw.get("id")
        if lat is None or lon is None or not isinstance(ident, str) or not ident:
            skipped["no_position"] += 1
            continue
        if scope is not None and _distance_nm(
            float(scope["center_lat"]), float(scope["center_lon"]), lat, lon
        ) > float(scope["radius_nm"]):
            skipped["outside_scope"] += 1
            continue
        seen_pos = _num(raw.get("seenPos"))
        if seen_pos is None or seen_pos < 0:
            skipped["no_position_age"] += 1
            continue
        observed_at = fetched_at - timedelta(seconds=seen_pos)
        position_age = (received_at - observed_at).total_seconds()
        if position_age > max_position_age:
            skipped["stale_position"] += 1
            continue

        row_id = f"flysdown:{source}:{int(fetched_ms)}:{ident}"
        on_ground = raw.get("onGround") is True
        states.append(AircraftState(
            icao24=ident.lower(),
            timestamp=observed_at,
            lat=lat,
            lon=lon,
            alt_baro_ft=_num(raw.get("alt")),
            alt_geom_ft=_num(raw.get("altGeom")),
            ground_speed_kt=_num(raw.get("groundSpeed")),
            track_deg=_num(raw.get("track")),
            callsign=_text(raw.get("callsign")),
            squawk=_text(raw.get("squawk")),
            emitter_category=_text(raw.get("category")),
            nic=None,
            nac_p=None,
            on_ground=on_ground,
            source_row_id=row_id,
        ))
        timing[row_id] = StateTiming(observed_at, TIMESTAMP_BASIS, seen_pos, position_age)

    return FeedBatch(
        _status(FRESH, None, payload, fetched_at, age_s),
        tuple(states),
        timing,
        dict(skipped),
    )


def _status(
    status: str,
    reason: str | None,
    payload: Mapping[str, Any] | None = None,
    fetched_at: datetime | None = None,
    age_s: float | None = None,
) -> FeedStatus:
    payload = payload or {}
    count = payload.get("count")
    return FeedStatus(
        status=status,
        reason=reason,
        source=_text(payload.get("source")),
        via=_text(payload.get("via")),
        fetched_at=fetched_at,
        snapshot_age_s=age_s,
        server_age_ms=_num(payload.get("ageMs")),
        count=int(count) if isinstance(count, int) else 0,
    )


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    out = float(value)
    return out if out == out and abs(out) != float("inf") else None


def _text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


def _distance_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    d_lat, d_lon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * _EARTH_RADIUS_NM * asin(min(1.0, sqrt(a)))
