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
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from shapely.geometry import shape

from ..types import Activation, AirspaceZone, Datum, TimeWindow, ZoneType

# Surface-to-unlimited, used only when a zone has no parseable band.
_UNLIMITED_FT = 99999.0


def load_zones(path: str | Path) -> list[AirspaceZone]:
    """Parse ``path`` into :class:`AirspaceZone` records.

    Raises:
        FileNotFoundError: ``path`` does not exist.
        ValueError: Not a FeatureCollection, a non-polygon geometry, an unknown
            zone type, datum or activation, or an unparseable window.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError(f"{path}: not a GeoJSON FeatureCollection")
    features = data.get("features")
    if not isinstance(features, list):
        raise ValueError(f"{path}: FeatureCollection has no features list")
    return [_zone(feature, index) for index, feature in enumerate(features)]


def _zone(feature: Mapping[str, Any], index: int) -> AirspaceZone:
    props: Mapping[str, Any] = feature.get("properties") or {}
    zone_id = str(props.get("zone_id") or f"zone-{index}")
    geometry = feature.get("geometry") or {}
    if geometry.get("type") not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"{zone_id}: geometry must be a Polygon or MultiPolygon")
    geom = shape(geometry)
    if not geom.is_valid:
        raise ValueError(f"{zone_id}: polygon is not valid")

    floor_ft, floor_datum = _limit(props, "floor", default_ft=0.0, default_datum=Datum.SFC)
    ceiling_ft, ceiling_datum = _limit(
        props, "ceiling", default_ft=_UNLIMITED_FT, default_datum=Datum.MSL
    )
    return AirspaceZone(
        zone_id=zone_id,
        name=str(props.get("name") or zone_id),
        zone_type=ZoneType(str(props.get("zone_type"))),
        geometry=geom,
        floor_ft=floor_ft,
        floor_datum=floor_datum,
        ceiling_ft=ceiling_ft,
        ceiling_datum=ceiling_datum,
        activation=Activation(str(props.get("activation"))),
        active_windows=tuple(_window(w, zone_id) for w in props.get("active_windows") or ()),
        controlling_agency=props.get("controlling_agency") or None,
        source=str(props.get("source") or ""),
        source_asof=date.fromisoformat(props["source_asof"]) if props.get("source_asof") else None,
    )


def _limit(
    props: Mapping[str, Any], key: str, *, default_ft: float, default_datum: Datum
) -> tuple[float, Datum]:
    """A missing or unparseable limit over-includes: SFC floor, unlimited ceiling."""
    raw_ft = props.get(f"{key}_ft")
    raw_datum = props.get(f"{key}_datum")
    if raw_ft is None:
        return default_ft, default_datum
    try:
        value = float(raw_ft)
    except (TypeError, ValueError):
        return default_ft, default_datum
    datum = Datum(str(raw_datum)) if raw_datum is not None else Datum.MSL
    return (0.0 if datum is Datum.SFC else value), datum


def _window(raw: Mapping[str, Any], zone_id: str) -> TimeWindow:
    try:
        start = datetime.fromisoformat(str(raw["start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(raw["end"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"{zone_id}: unparseable active window {raw!r}") from exc
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError(f"{zone_id}: active window must be tz-aware")
    return TimeWindow(start=start.astimezone(UTC), end=end.astimezone(UTC))
