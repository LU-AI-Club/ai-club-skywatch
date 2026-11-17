"""Stream B - airspace zone loader.

Parses FAA Special Use Airspace GeoJSON plus the FAA TFR list into
:class:`AirspaceZone` records. NOT UDDS, which is drone-only.

Inputs
------
path:
    A GeoJSON FeatureCollection. Each feature needs a polygon geometry in
    EPSG:4326 (lon/lat order) and properties carrying the zone id, name, type,
    altitude floor/ceiling with their datums, and activation rule. Recurring
    schedules may include a timezone, weekdays, seasonal bounds, and solar
    events.

Outputs
-------
A list of :class:`AirspaceZone`. Everything parseable is returned; filtering to
``cfg["airspace"]["include_types"]`` is available through
:func:`load_filtered_zones`, which combines parsing with the configured policy.

Failure causes
--------------
FileNotFoundError
    ``path`` does not exist.
ValueError
    Not a FeatureCollection, a feature carries a geometry that is neither a
    Polygon nor a MultiPolygon, or a datum/zone type is invalid.

A missing altitude limit defaults outward, each side on its own: no floor means
the surface, no ceiling means unlimited. That over-includes rather than
silently dropping a restricted volume, which is the safe direction for a
detector, while keeping whichever limit the source did publish. A limit given
without a datum is read as MSL.

Window times without a timezone are read as UTC, matching the ADS-B loader, so
:func:`logic.activation.is_active` never compares naive and aware datetimes.

Notes
-----
``source_asof`` must be set from the publication cycle of the file:
:meth:`Config.baseline_version` pins it into every Detection, so a stale cycle
silently mislabels every result.
"""
from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shapely.geometry import shape

from ..config import Config
from ..types import (
    Activation,
    AirspaceZone,
    Datum,
    RecurringWindow,
    TimeWindow,
    ZoneType,
)

_POLYGON_TYPES = ("Polygon", "MultiPolygon")


def _utc(raw: str) -> datetime:
    """Parse an ISO time; no timezone means UTC. Always returns aware UTC."""
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _limit(value: Any, datum_raw: Any, missing: tuple[float, Datum]) -> tuple[float, Datum]:
    """One altitude limit. A missing value takes ``missing``; a value given
    without a datum is read as MSL."""
    if value is None:
        return missing
    return float(value), Datum(datum_raw) if datum_raw is not None else Datum.MSL


def _month_day(raw: str | None) -> tuple[int, int] | None:
    if raw is None:
        return None
    month, day = (int(part) for part in raw.split("-", maxsplit=1))
    date(2000, month, day)
    return month, day


def _recurring_window(raw: dict[str, Any]) -> RecurringWindow:
    """Parse one JSON recurring window into the immutable zone contract."""
    start_raw = raw.get("start_time")
    end_raw = raw.get("end_time")
    weekdays = tuple(int(day) for day in raw.get("weekdays", []))
    if any(day < 0 or day > 6 for day in weekdays):
        raise ValueError(f"recurring window has an invalid weekday: {weekdays!r}")
    return RecurringWindow(
        start_time=time.fromisoformat(start_raw) if start_raw is not None else None,
        end_time=time.fromisoformat(end_raw) if end_raw is not None else None,
        weekdays=weekdays,
        start_month_day=_month_day(raw.get("start_month_day")),
        end_month_day=_month_day(raw.get("end_month_day")),
        start_sunrise=bool(raw.get("start_sunrise", False)),
        end_sunset=bool(raw.get("end_sunset", False)),
        all_day=bool(raw.get("all_day", False)),
    )


def load_zones(path: str | Path) -> list[AirspaceZone]:
    """Parse ``path`` into :class:`AirspaceZone` records."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"airspace file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if data.get("type") != "FeatureCollection":
        raise ValueError(f"expected a FeatureCollection, got {data.get('type')!r}")

    zones: list[AirspaceZone] = []
    for feature in data.get("features", []):
        geom_json = feature.get("geometry", {})
        if geom_json.get("type") not in _POLYGON_TYPES:
            raise ValueError(f"unsupported geometry type: {geom_json.get('type')!r}")
        geometry = shape(geom_json)

        props = feature.get("properties", {})

        floor_ft, floor_datum = _limit(
            props.get("floor_ft"), props.get("floor_datum"), (0.0, Datum.SFC)
        )
        ceiling_ft, ceiling_datum = _limit(
            props.get("ceiling_ft"), props.get("ceiling_datum"), (float("inf"), Datum.MSL)
        )

        active_windows = tuple(
            TimeWindow(start=_utc(w["start"]), end=_utc(w["end"]))
            for w in props.get("active_windows", [])
        )
        recurring_windows = tuple(
            _recurring_window(window) for window in props.get("recurring_windows", [])
        )
        schedule_timezone = str(props.get("schedule_timezone") or "UTC")
        if recurring_windows:
            try:
                ZoneInfo(schedule_timezone)
            except ZoneInfoNotFoundError as exc:
                raise ValueError(
                    f"unknown schedule timezone {schedule_timezone!r} "
                    f"for zone {props['zone_id']!r}"
                ) from exc

        source_asof_raw = props.get("source_asof")
        source_asof = date.fromisoformat(source_asof_raw) if source_asof_raw else None

        zone = AirspaceZone(
            zone_id=props["zone_id"],
            name=props.get("name", ""),
            zone_type=ZoneType(props["zone_type"]),
            geometry=geometry,
            floor_ft=floor_ft,
            floor_datum=floor_datum,
            ceiling_ft=ceiling_ft,
            ceiling_datum=ceiling_datum,
            activation=Activation(props["activation"]),
            active_windows=active_windows,
            recurring_windows=recurring_windows,
            schedule_timezone=schedule_timezone,
            unknown_outside_schedule=bool(props.get("unknown_outside_schedule", False)),
            unknown_within_schedule=bool(props.get("unknown_within_schedule", False)),
            controlling_agency=props.get("controlling_agency"),
            source=props.get("source", ""),
            source_asof=source_asof,
        )
        zones.append(zone)

    return zones


def filter_zones(zones: Sequence[AirspaceZone], cfg: Config) -> list[AirspaceZone]:
    """Keep only configured zone types; a missing setting includes every type."""
    include_types = cfg["airspace"].get(
        "include_types", [zone_type.value for zone_type in ZoneType]
    )
    included_types = {ZoneType(zone_type) for zone_type in include_types}
    return [zone for zone in zones if zone.zone_type in included_types]


def load_filtered_zones(path: str | Path, cfg: Config) -> list[AirspaceZone]:
    """Load zones from ``path`` and apply ``airspace.include_types``.

    An absent setting includes every zone type; an empty list includes none.
    """
    return filter_zones(load_zones(path), cfg)