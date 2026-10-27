"""Turn live FAA Special Use Airspace into the no-fly-zone loader's GeoJSON.

Replaces the three hand-drawn fixture zones with the real thing. Reads the FAA
Aeronautical Information Services SUA feature service, keeps the zones within
``scope.radius_nm`` of ``scope.center_*`` from the detector config, maps the FAA
attributes onto the properties ``ingest/airspace_loader.py`` expects, and writes
one GeoJSON FeatureCollection.

    AIRSPACE=air/detectors/no_fly_zone/fixtures/airspace
    python scripts/make_faa_airspace.py --out $AIRSPACE/klyh-150nm-faa.geojson
    python scripts/make_faa_airspace.py --sample 6 --out <path>   # a small test fixture

The service is the only network in the repo outside the collector, which is why
this is a script you run deliberately rather than anything the detector imports.
Output is sorted by zone_id, so re-running on the same cycle gives an identical
file and a clean diff.

Source
------
FAA AIS "Special Use Airspace", published on an eight-week cycle:
https://adds-faa.opendata.arcgis.com/datasets/faa::special-use-airspace

The FAA attributes, and what they turn into
-------------------------------------------
=====================  ==================================================
FAA field              loader property
=====================  ==================================================
NAME                   zone_id (de-duplicated) and name
TYPE_CODE              zone_type   P/R/W/A/MOA -> the ZoneType enum
LOWER_VAL/UOM/CODE     floor_ft / floor_datum
UPPER_VAL/UOM/CODE     ceiling_ft / ceiling_datum
TIMESOFUSE             activation (and kept verbatim as times_of_use)
CONT_AGENT             controlling_agency
=====================  ==================================================

Three things the real data does that the fixtures never did:

``SFC`` is a height, not always zero
    The FAA writes "300 FT SFC" for Farmville MOA's floor, meaning 300 ft
    *above the surface*. Only a value of 0 is literally the surface. So a
    non-zero SFC maps to :attr:`Datum.AGL`, and ``geo/altitude.py`` abstains on
    AGL because the detector has no terrain model. Those zones therefore never
    fire, which is the honest outcome rather than comparing an AGL floor to an
    MSL altitude. 17 of the 52 zones in range are in this position.

``STD`` means flight level
    "180 FL STD" is FL180. Stored as feet (18000) with :attr:`Datum.FL`, which
    is what types.py specifies.

``UNLTD`` / ``-9998`` means no ceiling
    Stored as infinity, so the vertical check can never exclude on the top.

Names repeat
    R-4006 appears four times and FARMVILLE MOA three, as separate sub-areas
    with different altitude bands. ``logic/detector.py`` builds
    ``{zone.zone_id: zone}``, so identical ids would silently drop every
    duplicate but one. Repeats get a ``#2``, ``#3`` suffix ordered by altitude
    band, which is stable across runs.

Activation is only ever a guess from free text
    TIMESOFUSE is prose: "CONTINUOUS", "0800 - 1700, MON - FRI; O/T BY NOTAM",
    "INTERMITTENT BY NOTAM", "SUNRISE - SUNSET, DAILY", "MAY 1 - SEP 15,
    CONTINUOUS; OTHER TIMES BY NOTAM". Only CONTINUOUS is unambiguous. Anything
    with clock times becomes SCHEDULED and anything else NOTAM, and **neither
    gets active_windows** - parsing a recurring schedule is gap 11. Until then
    those zones report UNKNOWN activation, which caps severity at
    ``severity.unknown_activation_cap``. The verbatim text rides along as
    ``times_of_use`` so an analyst can read what we could not parse.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SERVICE_URL = (
    "https://services6.arcgis.com/ssFJjBXIUyZDrSYZ/ArcGIS/rest/services/"
    "Special_Use_Airspace/FeatureServer/0/query"
)
# Cycle the data was published on. Printed into every Detection through
# Config.baseline_version, so it travels with the results.
DEFAULT_ASOF = "2026-09-28"
SOURCE = "faa_sua"

OUT_FIELDS = (
    "NAME,TYPE_CODE,LOWER_VAL,LOWER_UOM,LOWER_CODE,"
    "UPPER_VAL,UPPER_UOM,UPPER_CODE,TIMESOFUSE,CONT_AGENT,STATE,CITY"
)

# FAA TYPE_CODE -> the ZoneType enum in types.py. Every code the service
# returns is covered; an unknown one is reported rather than guessed.
ZONE_TYPES: dict[str, str] = {
    "P": "PROHIBITED",
    "R": "RESTRICTED",
    "W": "WARNING",
    "A": "ALERT",
    "MOA": "MOA",
}

_NM_PER_DEG_LAT = 60.0
_UNLIMITED = -9998  # the service's sentinel for "no upper limit"
# "0800 - 1700" or "0630 - SUNSET": a published clock schedule.
_CLOCK = re.compile(r"\d{3,4}\s*-\s*(\d{3,4}|SUNSET|SUNRISE)|SUNRISE\s*-\s*SUNSET")


def fetch_features(center_lat: float, center_lon: float, radius_nm: float) -> list[dict[str, Any]]:
    """Every SUA feature whose bounding box could fall within ``radius_nm``.

    A generous lat/lon envelope first, because the service has no distance
    filter; the exact test happens in :func:`within_radius_nm`.
    """
    pad_lat = radius_nm / _NM_PER_DEG_LAT
    pad_lon = pad_lat / max(math.cos(math.radians(center_lat)), 0.01)
    envelope = (
        f"{center_lon - pad_lon},{center_lat - pad_lat},"
        f"{center_lon + pad_lon},{center_lat + pad_lat}"
    )
    query = urllib.parse.urlencode({
        "geometry": envelope,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "f": "geojson",
    })
    with urllib.request.urlopen(f"{SERVICE_URL}?{query}", timeout=120) as response:
        payload = json.load(response)
    error = payload.get("error") or {}
    if error.get("code") == 429:
        # The service allows a few thousand request units a minute. Hitting it
        # is normal when iterating; it is not a bug in this script.
        raise SystemExit(
            f"FAA service rate limit: {error.get('message')}. Wait a minute and re-run."
        )
    if "features" not in payload:
        raise SystemExit(f"unexpected service response: {str(payload)[:300]}")
    features: list[dict[str, Any]] = payload["features"]
    return features


def within_radius_nm(
    geometry: dict[str, Any], center_lat: float, center_lon: float
) -> float:
    """Distance in nautical miles from the centre to the zone, 0.0 if inside.

    Same flat local projection ``geo/containment.py`` uses: degrees of
    longitude scaled by cos(latitude). Accurate enough over a few hundred nm.
    """
    import shapely
    from shapely.geometry import Point, shape

    x_scale = math.cos(math.radians(center_lat)) * _NM_PER_DEG_LAT
    local = shapely.transform(
        shape(geometry),
        lambda coords: (coords - (center_lon, center_lat)) * (x_scale, _NM_PER_DEG_LAT),
    )
    origin = Point(0.0, 0.0)
    return 0.0 if local.covers(origin) else float(local.distance(origin))


def altitude_limit(value: Any, uom: Any, code: Any, *, is_ceiling: bool) -> tuple[Any, str]:
    """One FAA altitude limit as ``(feet, datum)`` for the loader.

    ``None`` feet means "leave it out", which the loader reads as the surface
    for a floor and unlimited for a ceiling.
    """
    code = (str(code) if code is not None else "").strip().upper()
    unit = (str(uom) if uom is not None else "").strip().upper()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return (None, "MSL")

    if code == "UNLTD" or number == _UNLIMITED:
        return (None, "MSL") if is_ceiling else (0.0, "SFC")
    if code == "STD" or unit == "FL":
        # "180 FL STD" is FL180; types.py stores flight levels in feet.
        return number * 100.0, "FL"
    if code == "SFC":
        # Only zero is literally the surface. "300 FT SFC" is 300 ft AGL, and
        # the vertical check abstains on AGL for want of a terrain model.
        return (0.0, "SFC") if number == 0.0 else (number, "AGL")
    return number, "MSL"


def activation_for(times_of_use: Any) -> str:
    """Guess the activation rule from the FAA's free-text times of use.

    CONTINUOUS is the only unambiguous value. Clock times mean a published
    schedule we cannot yet parse into windows (gap 11), and everything else is
    NOTAM. Both of the latter end up UNKNOWN downstream, never a false ACTIVE.
    """
    text = (str(times_of_use) if times_of_use is not None else "").strip().upper()
    if not text:
        return "NOTAM"
    if "CONTINUOUS" in text and "NOTAM" not in text:
        return "ALWAYS"
    if _CLOCK.search(text):
        return "SCHEDULED"
    return "NOTAM"


#: Decimal places kept on every coordinate. The service returns up to 15, which
#: is sub-micron and makes the file several times larger for no benefit: 6 dp is
#: about 11 cm, far finer than any airspace boundary is surveyed or than the
#: position uncertainty the containment check already allows for.
_COORD_DP = 6


def round_coords(node: Any) -> Any:
    """Round every coordinate in a nested GeoJSON coordinate list."""
    if isinstance(node, list):
        return [round_coords(item) for item in node]
    if isinstance(node, float):
        return round(node, _COORD_DP)
    return node


def to_feature(
    raw: dict[str, Any], zone_id: str, asof: str
) -> dict[str, Any]:
    """One FAA feature as a loader-shaped GeoJSON feature."""
    props = raw["properties"]
    type_code = (props.get("TYPE_CODE") or "").strip().upper()
    if type_code not in ZONE_TYPES:
        raise SystemExit(f"unmapped FAA TYPE_CODE {type_code!r} on {zone_id!r}")

    floor_ft, floor_datum = altitude_limit(
        props.get("LOWER_VAL"), props.get("LOWER_UOM"), props.get("LOWER_CODE"),
        is_ceiling=False,
    )
    ceiling_ft, ceiling_datum = altitude_limit(
        props.get("UPPER_VAL"), props.get("UPPER_UOM"), props.get("UPPER_CODE"),
        is_ceiling=True,
    )

    out: dict[str, Any] = {
        "zone_id": zone_id,
        "name": (props.get("NAME") or "").strip(),
        "zone_type": ZONE_TYPES[type_code],
        "activation": activation_for(props.get("TIMESOFUSE")),
        "source": SOURCE,
        "source_asof": asof,
        # Not read by the loader. Kept so an analyst can see the schedule text
        # the detector could not parse, and gap 11 has something to work from.
        "times_of_use": (props.get("TIMESOFUSE") or "").strip() or None,
    }
    if floor_ft is not None:
        out["floor_ft"] = floor_ft
        out["floor_datum"] = floor_datum
    if ceiling_ft is not None:
        out["ceiling_ft"] = ceiling_ft
        out["ceiling_datum"] = ceiling_datum
    agency = (props.get("CONT_AGENT") or "").strip()
    if agency:
        out["controlling_agency"] = agency

    geometry = dict(raw["geometry"])
    geometry["coordinates"] = round_coords(geometry.get("coordinates"))
    return {"type": "Feature", "geometry": geometry, "properties": out}


def unique_zone_ids(features: list[dict[str, Any]]) -> list[str]:
    """One id per feature, suffixed where the FAA reuses a name.

    R-4006 is four separate sub-areas with different bands. ``logic/detector.py``
    keys zones by id, so duplicates would silently drop all but one. Ordered by
    altitude band so the suffix is the same on every run.
    """
    def band(feature: dict[str, Any]) -> tuple[float, float]:
        props = feature["properties"]
        def number(key: str) -> float:
            try:
                return float(props.get(key))
            except (TypeError, ValueError):
                return 0.0
        return number("LOWER_VAL"), number("UPPER_VAL")

    buckets: dict[str, list[int]] = defaultdict(list)
    for index, feature in enumerate(features):
        buckets[(feature["properties"].get("NAME") or "UNNAMED").strip()].append(index)

    ids: list[str] = [""] * len(features)
    for name, indexes in buckets.items():
        if len(indexes) == 1:
            ids[indexes[0]] = name
            continue
        for rank, index in enumerate(sorted(indexes, key=lambda i: band(features[i])), start=1):
            ids[index] = name if rank == 1 else f"{name} #{rank}"
    return ids


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--config", type=Path, default=None, help="detector config for scope")
    parser.add_argument(
        "--asof", default=DEFAULT_ASOF, help=f"SUA cycle date (default {DEFAULT_ASOF})"
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="keep only the N nearest zones, for a small committed test fixture",
    )
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "comma-separated FAA NAMEs to keep. The committed test sample uses this "
            "rather than --sample: the nearest zones are all SCHEDULED MOAs, so they "
            "exercise one code path out of several"
        ),
    )
    args = parser.parse_args(argv)

    from air.detectors.no_fly_zone.config import DEFAULT_PATH, load_config

    cfg = load_config(args.config or DEFAULT_PATH)
    scope = cfg["scope"]
    lat, lon, radius = (
        float(scope["center_lat"]), float(scope["center_lon"]), float(scope["radius_nm"])
    )
    print(f"scope: {scope['center_name']} ({lat}, {lon}) r={radius} nm, cycle {args.asof}")

    raw = fetch_features(lat, lon, radius)
    print(f"fetched {len(raw)} features from the FAA service")

    in_range = [(within_radius_nm(f["geometry"], lat, lon), f) for f in raw]
    in_range = [(d, f) for d, f in in_range if d <= radius]
    in_range.sort(key=lambda pair: pair[0])
    print(f"within {radius:g} nm: {len(in_range)}")
    if args.only:
        wanted = {name.strip().upper() for name in args.only.split(",")}
        in_range = [
            pair for pair in in_range
            if (pair[1]["properties"].get("NAME") or "").strip().upper() in wanted
        ]
        found = {(p[1]["properties"].get("NAME") or "").strip().upper() for p in in_range}
        missing = sorted(wanted - found)
        if missing:
            raise SystemExit(f"--only named zones that are not in range: {missing}")
        print(f"kept {len(in_range)} feature(s) for {len(wanted)} named zone(s)")
    if args.sample is not None:
        in_range = in_range[: args.sample]
        print(f"sampled the {len(in_range)} nearest")

    features = [f for _, f in in_range]
    ids = unique_zone_ids(features)
    mapped = [to_feature(f, zone_id, args.asof) for f, zone_id in zip(features, ids, strict=True)]
    mapped.sort(key=lambda f: f["properties"]["zone_id"])

    # Compact, but one feature per line: indenting every coordinate multiplies
    # the file size several times over, while a line per zone keeps a diff
    # readable at the granularity anyone actually reviews - which zone changed.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    lines = ",\n".join(json.dumps(f, separators=(",", ":")) for f in mapped)
    args.out.write_text(
        '{"type":"FeatureCollection","features":[\n' + lines + "\n]}\n",
        encoding="utf-8",
    )

    types = defaultdict(int)
    activations = defaultdict(int)
    agl = 0
    for feature in mapped:
        props = feature["properties"]
        types[props["zone_type"]] += 1
        activations[props["activation"]] += 1
        if "AGL" in (props.get("floor_datum"), props.get("ceiling_datum")):
            agl += 1
    print(f"wrote {args.out} ({len(mapped)} zones)")
    print(f"  types:       {dict(sorted(types.items()))}")
    print(f"  activation:  {dict(sorted(activations.items()))}")
    print(f"  AGL limits:  {agl} zone(s) - these abstain in the vertical check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
