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
``cfg["airspace"]["include_types"]`` is the caller's policy decision, not a
parsing one.

Failure causes
--------------
FileNotFoundError
    ``path`` does not exist.
ValueError
    Not a FeatureCollection, a feature carries a non-polygon geometry, or a
    datum is not a member of :class:`Datum`.

A zone with no parseable altitude band defaults to surface-to-unlimited. That
over-includes rather than silently dropping a restricted volume, which is the
safe direction for a detector.

Notes
-----
``source_asof`` must be set from the publication cycle of the file:
:meth:`Config.baseline_version` pins it into every Detection, so a stale cycle
silently mislabels every result.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from shapely.geometry import shape

from ..types import Activation, AirspaceZone, Datum, TimeWindow, ZoneType


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
        if geom_json.get("type") != "Polygon":
            raise ValueError(f"unsupported geometry type: {geom_json.get('type')!r}")
        geometry = shape(geom_json)

        props = feature.get("properties", {})

        floor_ft = props.get("floor_ft")
        ceiling_ft = props.get("ceiling_ft")
        floor_datum_raw = props.get("floor_datum")
        ceiling_datum_raw = props.get("ceiling_datum")

        if None in (floor_ft, ceiling_ft, floor_datum_raw, ceiling_datum_raw):
            floor_ft = 0.0
            floor_datum = Datum.SFC
            ceiling_ft = float("inf")
            ceiling_datum = Datum.MSL
        else:
            floor_datum = Datum(floor_datum_raw)
            ceiling_datum = Datum(ceiling_datum_raw)

        active_windows = tuple(
            TimeWindow(
                start=datetime.fromisoformat(w["start"]),
                end=datetime.fromisoformat(w["end"]),
            )
            for w in props.get("active_windows", [])
        )

        source_asof_raw = props.get("source_asof")
        source_asof = date.fromisoformat(source_asof_raw) if source_asof_raw else None

        zone = AirspaceZone(
            zone_id=props["zone_id"],
            name=props.get("name", ""),
            zone_type=ZoneType(props["zone_type"]),
            geometry=geometry,
            floor_ft=float(floor_ft),
            floor_datum=floor_datum,
            ceiling_ft=float(ceiling_ft),
            ceiling_datum=ceiling_datum,
            activation=Activation(props["activation"]),
            active_windows=active_windows,
            controlling_agency=props.get("controlling_agency"),
            source=props.get("source", ""),
            source_asof=source_asof,
        )
        zones.append(zone)

    return zones