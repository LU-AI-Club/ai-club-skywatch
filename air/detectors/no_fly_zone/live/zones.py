"""Map Flys Down's /data/zones.json into :class:`AirspaceZone` records.

The file is Flys Down's own, not the fixture schema stream B reads, so it gets
its own adapter. What it carries (see flysdown tools/fetch-zones.mjs):

- ``kind``: prohibited, tfr, sfra, custom
- Polygon geometry, or a Point with ``radiusNm`` for circles
- ``floorFt``/``ceilingFt`` in feet MSL, with ``agl: true`` when the published
  limits are above ground level
- ``note``: for FAA prohibited areas, the FAA TIMESOFUSE and REMARKS fields
- ``meta.updated`` and a disclaimer that activation times, NOTAMs and temporary
  restrictions are not modeled and geometry is simplified

Activation, honestly
--------------------
Flys Down does not model activation. The one real activation fact in the file
is FAA's published times of use: a prohibited area whose note is exactly
``CONTINUOUS`` is mapped to :attr:`Activation.ALWAYS`, when
``zones.trust_published_continuous`` allows it. Everything else, including the
standing Disney TFRs whose NOTAM we do not read, is :attr:`Activation.NOTAM`,
which stream E reports as UNKNOWN. Missing activation data is never read as
active.

Skipped, with a reason: the DC SFRA (a flight-rules area that transiting
traffic uses routinely, which Flys Down itself does not alert on) and custom
demonstration areas.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from math import asin, atan2, cos, degrees, pi, radians, sin
from typing import Any

from shapely.geometry import Polygon, shape

from ..types import Activation, AirspaceZone, Datum, ZoneType

SOURCE = "flysdown:/data/zones.json"
_EARTH_RADIUS_NM = 3440.065
_KIND_TO_TYPE = {"prohibited": ZoneType.PROHIBITED, "tfr": ZoneType.TFR}
_SKIP_KINDS = {
    "sfra": "flight-rules area, not a no-fly zone (Flys Down does not alert on it either)",
    "custom": "demonstration watch area, not an official restriction",
}
PUBLISHED_CONTINUOUS = "CONTINUOUS"


@dataclass(frozen=True, slots=True)
class ZoneBatch:
    zones: tuple[AirspaceZone, ...]
    activation_basis: Mapping[str, str] = field(default_factory=dict)
    skipped: tuple[tuple[str, str], ...] = ()
    asof: date | None = None
    disclaimer: str | None = None


def map_zones(geojson: Any, zones_cfg: Mapping[str, Any]) -> ZoneBatch:
    """Convert the file, recording why any feature was left out.

    Raises:
        ValueError: Not a FeatureCollection. An empty zone set would make
            every aircraft look clean, so it is an error, not an empty batch.
    """
    if not isinstance(geojson, Mapping) or geojson.get("type") != "FeatureCollection":
        raise ValueError("zones.json is not a GeoJSON FeatureCollection")
    meta: Mapping[str, Any] = geojson.get("meta") or {}
    asof = _date(meta.get("updated"))
    trust_continuous = bool(zones_cfg["trust_published_continuous"])
    segments = int(zones_cfg["circle_segments"])

    zones: list[AirspaceZone] = []
    basis: dict[str, str] = {}
    skipped: list[tuple[str, str]] = []
    for feature in geojson.get("features") or []:
        props: Mapping[str, Any] = (feature or {}).get("properties") or {}
        zone_id = str(props.get("id") or "unnamed")
        kind = str(props.get("kind") or "")
        if kind in _SKIP_KINDS:
            skipped.append((zone_id, _SKIP_KINDS[kind]))
            continue
        if kind not in _KIND_TO_TYPE:
            skipped.append((zone_id, f"unrecognized kind {kind!r}"))
            continue
        if "aircraft" not in (props.get("appliesTo") or ["aircraft"]):
            skipped.append((zone_id, "does not apply to aircraft"))
            continue
        geometry = _geometry(feature.get("geometry") or {}, props, segments)
        if geometry is None:
            skipped.append((zone_id, "no usable polygon or circle geometry"))
            continue
        floor = _num(props.get("floorFt"))
        ceiling = _num(props.get("ceilingFt"))
        if ceiling is None:
            skipped.append((zone_id, "no ceiling published"))
            continue
        agl = props.get("agl") is True
        floor_ft = floor or 0.0
        floor_datum = Datum.SFC if floor_ft == 0 else (Datum.AGL if agl else Datum.MSL)
        ceiling_datum = Datum.AGL if agl else Datum.MSL

        note = str(props.get("note") or "").strip()
        if kind == "prohibited" and note == PUBLISHED_CONTINUOUS and trust_continuous:
            activation = Activation.ALWAYS
            basis[zone_id] = (
                "FAA SUA times of use: CONTINUOUS (published schedule; "
                "NOTAMs and waivers not checked)"
            )
        else:
            activation = Activation.NOTAM
            basis[zone_id] = (
                "no activation data in Flys Down zones.json; treated as unknown"
                if kind != "prohibited" or note != PUBLISHED_CONTINUOUS
                else "published continuous, but trust_published_continuous is off"
            )

        zones.append(AirspaceZone(
            zone_id=zone_id,
            name=str(props.get("name") or zone_id),
            zone_type=_KIND_TO_TYPE[kind],
            geometry=geometry,
            floor_ft=floor_ft,
            floor_datum=floor_datum,
            ceiling_ft=ceiling,
            ceiling_datum=ceiling_datum,
            activation=activation,
            source=SOURCE,
            source_asof=asof,
        ))

    disclaimer = meta.get("disclaimer")
    return ZoneBatch(
        tuple(zones), basis, tuple(skipped), asof, str(disclaimer) if disclaimer else None
    )


def _geometry(geom: Mapping[str, Any], props: Mapping[str, Any], segments: int) -> Any:
    kind = geom.get("type")
    if kind in ("Polygon", "MultiPolygon"):
        out = shape(geom)
        return out if out.is_valid and not out.is_empty else None
    radius = _num(props.get("radiusNm"))
    if kind == "Point" and radius and radius > 0:
        lon, lat = geom["coordinates"][:2]
        return _circle(float(lat), float(lon), radius, segments)
    return None


def _circle(lat: float, lon: float, radius_nm: float, segments: int) -> Polygon:
    """Geodesic circle as a polygon, lon/lat order."""
    d = radius_nm / _EARTH_RADIUS_NM
    lat1, lon1 = radians(lat), radians(lon)
    points = []
    for i in range(segments):
        bearing = 2 * pi * i / segments
        lat2 = asin(sin(lat1) * cos(d) + cos(lat1) * sin(d) * cos(bearing))
        lon2 = lon1 + atan2(sin(bearing) * sin(d) * cos(lat1), cos(d) - sin(lat1) * sin(lat2))
        points.append((degrees(lon2), degrees(lat2)))
    return Polygon(points)


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None
