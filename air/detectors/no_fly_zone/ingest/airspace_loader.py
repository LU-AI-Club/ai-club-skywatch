"""Stream B - airspace zone loader.

Parses FAA Special Use Airspace GeoJSON plus the FAA TFR list into
:class:`AirspaceZone` records. NOT UDDS, which is drone-only.

Inputs
------
path:
    A GeoJSON FeatureCollection. Each feature needs a polygon geometry in
    EPSG:4326 (lon/lat order) and properties carrying the zone id, name, type,
    altitude floor/ceiling with their datums, and activation rule.

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
    Polygon nor a MultiPolygon, a datum/zone type is invalid, or a terrain
    bound is half given or has its minimum above its maximum.

A missing altitude limit defaults outward, each side on its own: no floor means
the surface, no ceiling means unlimited. That over-includes rather than
silently dropping a restricted volume, which is the safe direction for a
detector, while keeping whichever limit the source did publish. A limit given
without a datum is read as MSL.

Terrain: optional ``terrain_min_ft`` / ``terrain_max_ft`` properties give the
lowest and highest ground elevation under the zone in ft MSL, which is what
lets ``geo/altitude.py`` place an AGL floor. Give both or neither.
:func:`load_filtered_zones` fills zones that have an AGL limit and no bound of
their own from ``geometry.terrain_fallback_ft`` in the config, when it is set.

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
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from ..config import Config
from ..types import Activation, AirspaceZone, Datum, TimeWindow, ZoneType

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


def _terrain(props: dict[str, Any], zone_id: Any) -> tuple[float | None, float | None]:
    """The zone's terrain bound in ft MSL, or (None, None) when it has none."""
    low, high = props.get("terrain_min_ft"), props.get("terrain_max_ft")
    if low is None and high is None:
        return None, None
    if low is None or high is None:
        raise ValueError(f"zone {zone_id}: give both terrain_min_ft and terrain_max_ft")
    if float(low) > float(high):
        raise ValueError(f"zone {zone_id}: terrain_min_ft is above terrain_max_ft")
    return float(low), float(high)


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

        source_asof_raw = props.get("source_asof")
        source_asof = date.fromisoformat(source_asof_raw) if source_asof_raw else None

        terrain_min_ft, terrain_max_ft = _terrain(props, props.get("zone_id"))

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
            controlling_agency=props.get("controlling_agency"),
            source=props.get("source", ""),
            source_asof=source_asof,
            terrain_min_ft=terrain_min_ft,
            terrain_max_ft=terrain_max_ft,
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


def apply_terrain_fallback(zones: Sequence[AirspaceZone], cfg: Config) -> list[AirspaceZone]:
    """Give AGL zones with no terrain bound the config's area-wide one.

    ``geometry.terrain_fallback_ft`` is a ``{min, max}`` pair in ft MSL that
    holds anywhere the zones can be. Zones that carry their own bound, and
    zones with no AGL limit, are returned untouched. With the setting absent
    nothing changes, and AGL zones without a bound keep abstaining.
    """
    fallback = cfg.raw.get("geometry", {}).get("terrain_fallback_ft")
    if not fallback:
        return list(zones)
    low, high = float(fallback["min"]), float(fallback["max"])
    return [
        replace(zone, terrain_min_ft=low, terrain_max_ft=high)
        if Datum.AGL in (zone.floor_datum, zone.ceiling_datum)
        and zone.terrain_min_ft is None
        else zone
        for zone in zones
    ]


def load_filtered_zones(path: str | Path, cfg: Config) -> list[AirspaceZone]:
    """Load zones from ``path``, apply ``airspace.include_types`` and the terrain fallback.

    An absent ``include_types`` includes every zone type; an empty list
    includes none. See :func:`apply_terrain_fallback` for the terrain setting.
    """
    return apply_terrain_fallback(filter_zones(load_zones(path), cfg), cfg)