"""Stream I - live ADS-B collector. A SEPARATE PROCESS from the detector.

Polls our own receiver (dump1090 / AirNav) at ``sampling.target_hz`` and writes
hourly Parquet. The detector never talks to a network or a receiver; it reads
the files this produces. That separation is what keeps every detector function
pure and testable.

Inputs
------
url:
    Receiver endpoint, e.g. a dump1090 ``aircraft.json``.
out_dir:
    Directory for hourly Parquet files. Created if absent. Name files so they
    sort chronologically, e.g. ``states-2026-09-22T14.parquet``.
cfg:
    Supplies ``sampling.target_hz``. Passed in, never loaded here, like every
    other module in the package; ``cli.py`` is what reads the file.

Outputs
-------
``None``. The side effect is the files. This is the one module in the package
allowed to do network and disk I/O in normal operation.

Failure causes
--------------
OSError / connection errors
    Receiver unreachable. Log, back off, keep running - a collector that dies
    on one dropped connection loses the rest of the hour.
PermissionError
    ``out_dir`` not writable.

Never crash the loop on a single malformed poll. A gap in the data is
recoverable; a dead collector is not.

Notes
-----
Write the current hour to a temp name and rename on roll-over, so the detector
never reads a half-written file. Gaps longer than ``sampling.max_gap_sec``
break a track for dwell purposes, so record actual poll timestamps rather than
assuming a perfect 1 Hz cadence.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..config import Config

logger = logging.getLogger(__name__)

# Backoff after a failed poll: double each time, capped. A receiver that has
# been down for an hour must not be hammered once a second, and a collector
# that gives up loses the rest of the hour - so it waits, then keeps trying.
# Retry timing, not detector behaviour, so it is not a config value.
_BACKOFF_START_S = 1.0
_BACKOFF_MAX_S = 60.0
_HTTP_TIMEOUT_S = 10.0
# How long an already-written hour stays buffered in case a backdated position
# still lands in it. Memory bound for a long run, not detector behaviour.
_RETAIN_HOURS = timedelta(hours=2)

SCHEMA = pa.schema([
    ("icao24", pa.string()),
    ("timestamp", pa.timestamp("us", tz="UTC")),
    ("lat", pa.float64()),
    ("lon", pa.float64()),
    ("alt_baro_ft", pa.float64()),
    ("alt_geom_ft", pa.float64()),
    ("ground_speed_kt", pa.float64()),
    ("track_deg", pa.float64()),
    ("callsign", pa.string()),
    ("squawk", pa.string()),
    ("emitter_category", pa.string()),
    ("nic", pa.int32()),
    ("nac_p", pa.int32()),
    ("on_ground", pa.bool_()),
    ("source_row_id", pa.string()),
])


def hour_filename(hour: datetime) -> str:
    """Name that sorts chronologically, e.g. states-2026-09-22T14.parquet."""
    return f"states-{hour:%Y-%m-%dT%H}.parquet"


def write_hour(rows: list[dict[str, Any]], out_dir: str | Path, hour: datetime) -> Path:
    """Write ``rows`` to the file for ``hour`` and return its path.

    Writes to a temp name first, then renames, so a reader never sees a
    half-written file. Keys missing from a row are stored as null.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / hour_filename(hour)
    temp = out_dir / (final.name + ".tmp")
    pq.write_table(pa.Table.from_pylist(rows, schema=SCHEMA), temp)
    os.replace(temp, final)
    return final


def poll_once(url: str, timeout_s: float = _HTTP_TIMEOUT_S) -> dict[str, Any]:
    """Fetch and decode one ``aircraft.json`` from the receiver.

    Raises whatever the network or the decoder raises. Deciding that a failed
    poll is survivable belongs to :func:`collect`, not here.
    """
    with urllib.request.urlopen(url, timeout=timeout_s) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise ValueError(f"{url} did not return a JSON object")
    return payload


def _as_float(value: Any) -> float | None:
    """A number, or None for anything that is not one - including "ground"."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_int(value: Any) -> int | None:
    number = _as_float(value)
    return None if number is None else int(number)


def _as_text(value: Any) -> str | None:
    """Strip a string field. ADS-B pads callsigns out to 8 characters."""
    if not isinstance(value, str):
        return None
    return value.strip() or None


def parse_aircraft_json(
    payload: dict[str, Any], source: str, polled_at: datetime
) -> list[dict[str, Any]]:
    """Turn one poll into rows matching :data:`SCHEMA`.

    Pure: no network, no clock, no disk. ``polled_at`` is used only when the
    payload carries no ``now``, so a test can pin every timestamp.

    Field names are the dump1090-fa / readsb ``aircraft.json`` schema. VERIFY
    them against a capture from our own station before trusting a long run. An
    unexpected name reads as a missing field, which abstains rather than
    guessing - but it does so silently, which is the failure mode to watch.

    Four decisions worth knowing about:

    ``alt_baro`` may be the string ``"ground"``
        That is how ``aircraft.json`` reports an aircraft on the surface, and
        it is the only on-ground signal the feed carries. It becomes
        ``on_ground=True`` with no barometric altitude, which is what
        ``filters.drop_on_ground`` acts on.
    the timestamp is ``now - seen_pos``, not the poll time
        ``seen_pos`` is how many seconds ago the position was last updated.
        Stamping a stale position with the poll time would stretch an
        aircraft's dwell inside a zone and corrupt the ``max_gap_sec`` rule.
    aircraft with no position are dropped
        Mode S-only targets appear in the feed with no ``lat``/``lon``.
        ``AircraftState`` requires a position, so there is nothing to record.
    rows come back in feed order
        Dropping a position already recorded needs state across polls, so it
        lives in :func:`collect` rather than here.
    """
    now = _as_float(payload.get("now"))
    base = datetime.fromtimestamp(now, tz=UTC) if now is not None else polled_at

    rows: list[dict[str, Any]] = []
    for craft in payload.get("aircraft") or []:
        if not isinstance(craft, dict):
            continue
        icao24 = _as_text(craft.get("hex"))
        lat, lon = _as_float(craft.get("lat")), _as_float(craft.get("lon"))
        if icao24 is None or lat is None or lon is None:
            continue

        icao24 = icao24.lower()
        seen_pos = _as_float(craft.get("seen_pos")) or 0.0
        observed_at = base - timedelta(seconds=max(seen_pos, 0.0))
        raw_alt_baro = craft.get("alt_baro")

        rows.append({
            "icao24": icao24,
            "timestamp": observed_at,
            "lat": lat,
            "lon": lon,
            "alt_baro_ft": _as_float(raw_alt_baro),
            "alt_geom_ft": _as_float(craft.get("alt_geom")),
            "ground_speed_kt": _as_float(craft.get("gs")),
            "track_deg": _as_float(craft.get("track")),
            "callsign": _as_text(craft.get("flight")),
            "squawk": _as_text(craft.get("squawk")),
            "emitter_category": _as_text(craft.get("category")),
            "nic": _as_int(craft.get("nic")),
            "nac_p": _as_int(craft.get("nac_p")),
            "on_ground": raw_alt_baro == "ground",
            "source_row_id": f"{source}@{observed_at.isoformat()}#{icao24}",
        })
    return rows


def _hour_of(moment: datetime) -> datetime:
    """The UTC hour bucket a row belongs to."""
    return moment.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def collect(
    url: str,
    out_dir: str | Path,
    *,
    cfg: Config,
    max_polls: int | None = None,
    fetch: Callable[[str], dict[str, Any]] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> None:
    """Poll ``url`` and write hourly Parquet into ``out_dir``. Runs forever.

    ``cfg`` supplies ``sampling.target_hz``; no cadence is a literal here.

    The hour a row lands in comes from the row's own timestamp rather than the
    wall clock, so a position that arrives late is still filed under the hour it
    happened in. That is why rows are buffered **per hour** rather than one hour
    at a time: right at the top of an hour a single poll routinely carries both
    a fresh position and one backdated by ``seen_pos`` across the boundary, and
    those belong in different files. An hour is written out once a row for a
    later hour appears, and again if a late row lands in it afterwards -
    :func:`write_hour` replaces the file atomically from the full buffer, so
    rewriting is idempotent and never loses earlier rows. Whatever is still
    buffered is written when the loop stops, Ctrl-C included.

    ``max_polls``, ``fetch`` and ``sleep`` exist so the tests can drive the loop
    without a receiver and without real time passing. Left unset it polls the
    real URL at the configured rate, forever.

    A failed poll is logged and retried with growing backoff, never raised: a
    gap in the data is recoverable, a dead collector is not.
    """
    do_fetch = fetch if fetch is not None else poll_once
    do_sleep = sleep if sleep is not None else time.sleep
    interval_s = 1.0 / float(cfg["sampling"]["target_hz"])

    buffers: dict[datetime, list[dict[str, Any]]] = {}
    unwritten: set[datetime] = set()
    recorded: dict[str, datetime] = {}
    newest: datetime | None = None
    backoff_s = _BACKOFF_START_S
    polls = 0

    def flush(hour: datetime) -> None:
        logger.info("Writing %d rows for %s", len(buffers[hour]), hour)
        write_hour(buffers[hour], out_dir, hour)
        unwritten.discard(hour)

    try:
        while max_polls is None or polls < max_polls:
            polls += 1
            try:
                payload = do_fetch(url)
            except Exception as exc:  # noqa: BLE001 - any poll may fail; keep going
                logger.warning("Poll %d of %s failed: %s", polls, url, exc)
                do_sleep(backoff_s)
                backoff_s = min(backoff_s * 2.0, _BACKOFF_MAX_S)
                continue
            backoff_s = _BACKOFF_START_S

            for row in parse_aircraft_json(payload, url, datetime.now(tz=UTC)):
                # The same position is re-reported on every poll until it
                # changes. Keeping each copy would bloat the file and hand the
                # detector pairs zero seconds apart.
                icao24, observed_at = row["icao24"], row["timestamp"]
                if recorded.get(icao24) == observed_at:
                    continue
                recorded[icao24] = observed_at

                hour = _hour_of(observed_at)
                buffers.setdefault(hour, []).append(row)
                unwritten.add(hour)
                newest = hour if newest is None else max(newest, hour)

            # Any hour the stream has moved past is complete enough to write.
            for hour in sorted(h for h in unwritten if newest is not None and h < newest):
                flush(hour)
            # Keep recent hours buffered for late arrivals; drop the rest so a
            # run of days does not grow without bound.
            if newest is not None:
                for hour in [h for h in buffers if h < newest - _RETAIN_HOURS]:
                    if hour not in unwritten:
                        del buffers[hour]

            do_sleep(interval_s)
    except KeyboardInterrupt:  # pragma: no cover - interactive stop
        logger.info("Stopping %s on interrupt", url)
    finally:
        for hour in sorted(unwritten):
            flush(hour)


__all__ = [
    "SCHEMA",
    "collect",
    "hour_filename",
    "parse_aircraft_json",
    "poll_once",
    "write_hour",
]
