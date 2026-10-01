"""Map a readsb-style aggregator response (adsb.lol, adsb.fi) into states.

This is the run-it-yourself path: the runner asks the aggregator directly
from the user's own connection, so no server of anyone's sits in between.

Inputs
------
payload:
    Parsed JSON from ``/v2/lat/{lat}/lon/{lon}/dist/{nm}`` (adsb.lol) or
    ``/api/v3/lat/{lat}/lon/{lon}/dist/{nm}`` (adsb.fi)::

        {now (epoch ms), msg, total, ac: [{hex, flight, lat, lon, alt_baro,
         alt_geom, gs, track, squawk, category, nic, nac_p, seen, seen_pos}]}

received_at:
    When this process received the response (tz-aware UTC).

Timing
------
``now`` is the aggregator's own clock when it built the answer, and
``seen_pos`` is how old each position was at that moment, so the observation
time is ``now - seen_pos``. That is still an estimate, but a tighter one than
the Flys Down path: there is no relay hop in between. It is labeled with its
own basis. A record with no ``seen_pos`` is skipped, never stamped with
``now``.

Unlike the Flys Down feed, these responses carry NIC and NACp, so stream C
uses the real containment radius when it is reported.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from ..types import AircraftState
from .feed import (
    FRESH,
    STALE,
    UNAVAILABLE,
    FeedBatch,
    FeedStatus,
    StateTiming,
    _distance_nm,
    _num,
    _text,
)

TIMESTAMP_BASIS = "estimated: aggregator now minus seen_pos"
_MS_THRESHOLD = 1e11  # epoch values above this are milliseconds, below are seconds


def map_readsb(
    payload: Any,
    received_at: datetime,
    live_cfg: Mapping[str, Any],
    scope: Mapping[str, Any] | None = None,
    source: str = "adsb.lol",
) -> FeedBatch:
    """Turn one aggregator response into states, or a status saying why not.

    Raises:
        ValueError: ``received_at`` is naive.
    """
    if received_at.tzinfo is None:
        raise ValueError("received_at must be tz-aware UTC")

    def status(kind: str, reason: str | None, fetched: datetime | None = None,
               age: float | None = None, count: int = 0) -> FeedStatus:
        return FeedStatus(kind, reason, source, "direct", fetched, age, None, count)

    if not isinstance(payload, Mapping):
        return FeedBatch(status(UNAVAILABLE, "response was not a JSON object"))
    if payload.get("ok") is False:
        return FeedBatch(status(UNAVAILABLE, str(payload.get("error") or "request failed")[:200]))
    aircraft = payload.get("ac")
    now = _num(payload.get("now"))
    if not isinstance(aircraft, list):
        return FeedBatch(status(UNAVAILABLE, str(payload.get("msg") or "response had no ac list")))
    if now is None:
        return FeedBatch(status(UNAVAILABLE, "response had no 'now' time"))

    fetched_at = datetime.fromtimestamp(now / 1000 if now > _MS_THRESHOLD else now, tz=UTC)
    age_s = (received_at - fetched_at).total_seconds()
    max_age = float(live_cfg["max_snapshot_age_s"])
    if age_s > max_age:
        reason = f"aggregator answer is {age_s:.0f}s old (limit {max_age:.0f}s)"
        return FeedBatch(status(STALE, reason, fetched_at, age_s, len(aircraft)))

    max_position_age = float(live_cfg["max_position_age_s"])
    stamp = int(fetched_at.timestamp() * 1000)
    skipped: Counter[str] = Counter()
    states: list[AircraftState] = []
    timing: dict[str, StateTiming] = {}
    for raw in aircraft:
        if not isinstance(raw, Mapping):
            skipped["malformed_record"] += 1
            continue
        lat, lon, ident = _num(raw.get("lat")), _num(raw.get("lon")), raw.get("hex")
        if lat is None or lon is None or not isinstance(ident, str) or not ident:
            skipped["no_position"] += 1
            continue
        if scope is not None and _distance_nm(
            float(scope["center_lat"]), float(scope["center_lon"]), lat, lon
        ) > float(scope["radius_nm"]):
            skipped["outside_scope"] += 1
            continue
        seen_pos = _num(raw.get("seen_pos"))
        if seen_pos is None or seen_pos < 0:
            skipped["no_position_age"] += 1
            continue
        observed_at = fetched_at - timedelta(seconds=seen_pos)
        position_age = (received_at - observed_at).total_seconds()
        if position_age > max_position_age:
            skipped["stale_position"] += 1
            continue

        on_ground = raw.get("alt_baro") == "ground" or raw.get("alt_geom") == "ground"
        nic, nac_p = _num(raw.get("nic")), _num(raw.get("nac_p"))
        row_id = f"{source}:{stamp}:{ident}"
        states.append(AircraftState(
            icao24=ident.lower(),
            timestamp=observed_at,
            lat=lat,
            lon=lon,
            alt_baro_ft=_num(raw.get("alt_baro")),
            alt_geom_ft=_num(raw.get("alt_geom")),
            ground_speed_kt=_num(raw.get("gs")),
            track_deg=_num(raw.get("track")),
            callsign=_text(raw.get("flight")),
            squawk=_text(raw.get("squawk")),
            emitter_category=_text(raw.get("category")),
            nic=int(nic) if nic is not None else None,
            nac_p=int(nac_p) if nac_p is not None else None,
            on_ground=on_ground,
            source_row_id=row_id,
        ))
        timing[row_id] = StateTiming(observed_at, TIMESTAMP_BASIS, seen_pos, position_age)

    return FeedBatch(status(FRESH, None, fetched_at, age_s, len(aircraft)), tuple(states),
                     timing, dict(skipped))
