"""Stream J - Streamlit dashboard. Run with ``streamlit run dashboard/app.py``.

Read-only. Reads ``detections.jsonl`` and the Parquet state files and draws
them. It never computes a detection: if a number is interesting enough to show,
it belongs in the Detection the detector already emitted.

Inputs
------
Paths entered in the sidebar, defaulting to the CLI's output layout.

Panels
------
- A pydeck map: zone polygons, aircraft positions, detections marked.
- A detections table sorted by ``anomaly_score``, filterable by severity.
- Per-detection detail: ``explanation_facts`` and ``limitations`` verbatim.
- An exit-reason histogram, so a quiet run can be explained rather than
  assumed broken.

Failure causes
--------------
FileNotFoundError
    Inputs not produced yet. Show an empty state with the expected path, not a
    stack trace.
Malformed JSONL line
    Skip it, count it, surface the count. One bad line must not blank the page.

Notes
-----
Guard the Streamlit body behind ``if __name__ == "__main__":`` so importing
this module (as the tests do) does no I/O and renders nothing.

The loaders below are plain functions with no Streamlit in them, so they are
unit-tested directly. This file deliberately imports nothing from the detector
package: ``streamlit run`` executes it as a bare script, where the package's
relative imports would fail, and a read-only view has no business calling
detector code anyway.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = Path("out")
DEFAULT_AIRSPACE = PACKAGE_DIR / "fixtures" / "airspace" / "klyh-150nm.geojson"
DEFAULT_STATES = PACKAGE_DIR / "fixtures" / "tracks" / "klyh_mixed.json"

SEVERITY_ORDER = ("HIGH", "MEDIUM", "LOW", "INFO")

# RGBA, for pydeck. Detections by severity; zones by airspace type.
SEVERITY_COLOR: dict[str, list[int]] = {
    "HIGH": [214, 39, 40, 230],
    "MEDIUM": [255, 127, 14, 230],
    "LOW": [255, 199, 44, 230],
    "INFO": [31, 119, 180, 230],
}
ZONE_COLOR: dict[str, list[int]] = {
    "PROHIBITED": [214, 39, 40, 60],
    "RESTRICTED": [255, 127, 14, 55],
    "TFR": [148, 103, 189, 60],
    "WARNING": [140, 86, 75, 45],
    "ALERT": [140, 86, 75, 45],
    "MOA": [31, 119, 180, 40],
}
_FALLBACK_ZONE_COLOR = [127, 127, 127, 40]


# ----------------------------------------------------------------- loaders


@dataclass
class DetectionLoad:
    """What came out of ``detections.jsonl``, plus how much of it was usable."""

    path: Path
    rows: list[dict[str, Any]] = field(default_factory=list)
    bad_lines: int = 0
    missing: bool = False


def flatten_detection(record: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields the dashboard shows out of one platform-contract record.

    Raises KeyError/TypeError on a record that is not the platform shape; the
    caller counts that as a bad line.
    """
    meta = record["metadata"]
    extras = meta.get("extras") or {}
    centroid = (record.get("geospatial_context") or {}).get("centroid") or {}
    entities = record.get("entities_involved") or []
    entity_id = entities[0]["entity_id"] if entities else ""
    return {
        "observed_at": record["temporal_bounds"]["start_time"],
        "aircraft": entity_id.split(":", 1)[-1],
        "zone_id": extras.get("zone_id", ""),
        "severity": record["severity"],
        "anomaly_score": float(meta["anomaly_score"]),
        "confidence": float(record.get("confidence") or 0.0),
        "lat": _first_float(centroid.get("latitude"), extras.get("lat")),
        "lon": _first_float(centroid.get("longitude"), extras.get("lon")),
        "altitude_ft": centroid.get("altitude"),
        "penetration_nm": extras.get("penetration_nm"),
        "source_row_id": extras.get("source_row_id", ""),
        "explanation_facts": list(meta.get("explanation_facts") or []),
        "limitations": list(meta.get("limitations") or []),
    }


def _first_float(*values: Any) -> float:
    """The first value that is not None, as a float. Raises if all are None."""
    for value in values:
        if value is not None:
            return float(value)
    raise ValueError("no coordinate present")


def load_detections(path: str | Path) -> DetectionLoad:
    """Read ``detections.jsonl``. Never raises for a missing file or a bad line."""
    path = Path(path)
    result = DetectionLoad(path=path)
    if not path.is_file():
        result.missing = True
        return result
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                result.rows.append(flatten_detection(json.loads(line)))
            except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                result.bad_lines += 1
    rank = {sev: i for i, sev in enumerate(SEVERITY_ORDER)}
    result.rows.sort(key=lambda r: (-r["anomaly_score"], rank.get(r["severity"], 99)))
    return result


def load_exit_summary(path: str | Path) -> dict[str, Any] | None:
    """Read the CLI's ``exit_reasons.json``; ``None`` if absent or unreadable."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_zone_shapes(path: str | Path) -> list[dict[str, Any]] | None:
    """Zone polygons from GeoJSON as plain dicts for the map; ``None`` if absent.

    Reads the file directly rather than through stream B so the dashboard
    needs no shapely and cannot fail on a zone the loader would reject.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    shapes: list[dict[str, Any]] = []
    for feature in data.get("features", []) if isinstance(data, dict) else []:
        geom = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        if geom.get("type") == "Polygon":
            rings = [geom["coordinates"][0]]
        elif geom.get("type") == "MultiPolygon":
            rings = [poly[0] for poly in geom["coordinates"]]
        else:
            continue
        zone_type = str(props.get("zone_type", ""))
        for ring in rings:
            shapes.append({
                "zone_id": props.get("zone_id", ""),
                "name": props.get("name", ""),
                "zone_type": zone_type,
                "band": _band_label(props),
                "polygon": ring,
                "color": ZONE_COLOR.get(zone_type, _FALLBACK_ZONE_COLOR),
                "label": f"{props.get('zone_id', '')} ({zone_type})<br/>{_band_label(props)}",
            })
    return shapes


def load_state_points(path: str | Path) -> list[dict[str, Any]] | None:
    """Aircraft positions from a JSON array, a Parquet file, or a folder of
    Parquet files (the collector's hourly layout). ``None`` if nothing usable."""
    path = Path(path)
    if path.is_dir():
        files = sorted(path.glob("*.parquet"))
        if not files:
            return None
        rows = [row for f in files for row in _read_parquet(f)]
    elif path.suffix == ".parquet" and path.is_file():
        rows = _read_parquet(path)
    elif path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return None
        rows = loaded if isinstance(loaded, list) else []
    else:
        return None

    points: list[dict[str, Any]] = []
    for row in rows:
        try:
            alt = row.get("alt_geom_ft")
            if alt is None:
                alt = row.get("alt_baro_ft")
            icao24 = str(row.get("icao24", ""))
            callsign = row.get("callsign") or ""
            points.append({
                "icao24": icao24,
                "lat": float(row["lat"]),
                "lon": float(row["lon"]),
                "altitude_ft": alt,
                "callsign": callsign,
                "timestamp": str(row.get("timestamp", "")),
                "label": f"{icao24} {callsign}<br/>{_alt_label(alt)}",
            })
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    return points


def _read_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import pyarrow.parquet as pq
    except ImportError:
        return []
    try:
        rows: list[dict[str, Any]] = pq.read_table(path).to_pylist()
        return rows
    except Exception:  # noqa: BLE001 - one bad hourly file must not blank the map
        return []


def _alt_label(alt: Any) -> str:
    try:
        return f"{float(alt):,.0f} ft"
    except (TypeError, ValueError):
        return "altitude unknown"


def _band_label(props: dict[str, Any]) -> str:
    floor, ceiling = props.get("floor_ft"), props.get("ceiling_ft")
    if floor is None or ceiling is None:
        return "altitude band not published"
    return (
        f"{floor:,.0f} {props.get('floor_datum', '')} - "
        f"{ceiling:,.0f} {props.get('ceiling_datum', '')}"
    )


# ----------------------------------------------------------------- view


def main() -> None:
    """Render the dashboard. Called only under ``streamlit run``."""
    import pandas as pd
    import pydeck as pdk
    import streamlit as st

    st.set_page_config(page_title="SkyWatch - No-Fly-Zone", layout="wide")
    st.title("No-Fly-Zone Detector")

    with st.sidebar:
        st.header("Inputs")
        out_dir = Path(st.text_input("CLI output folder (--out)", str(DEFAULT_OUT_DIR)))
        airspace_path = Path(st.text_input("Airspace GeoJSON", str(DEFAULT_AIRSPACE)))
        states_path = Path(st.text_input(
            "Aircraft states (JSON, Parquet, or Parquet folder)", str(DEFAULT_STATES)
        ))
        st.caption("Produce the output folder with:")
        st.code(
            "python -m air.detectors.no_fly_zone run \\\n"
            f"  --input <adsb.json> --out {out_dir}",
            language="bash",
        )

    detections = load_detections(out_dir / "detections.jsonl")
    exit_summary = load_exit_summary(out_dir / "exit_reasons.json")
    zones = load_zone_shapes(airspace_path)
    states = load_state_points(states_path)

    if detections.missing:
        st.info(
            f"No detections file yet at `{detections.path}`. "
            "Run the CLI (command in the sidebar), then refresh."
        )
    if detections.bad_lines:
        st.warning(f"Skipped {detections.bad_lines} malformed line(s) in `{detections.path}`.")

    # ---- headline numbers
    by_sev = {sev: sum(r["severity"] == sev for r in detections.rows) for sev in SEVERITY_ORDER}
    cols = st.columns(5)
    cols[0].metric("States loaded", exit_summary["states"] if exit_summary else "—")
    cols[1].metric("Detections", len(detections.rows))
    for col, sev in zip(cols[2:], ("HIGH", "MEDIUM", "LOW"), strict=True):
        col.metric(sev.title(), by_sev[sev])

    # ---- filter, shared by map and table
    severities = st.multiselect("Severity", SEVERITY_ORDER, default=list(SEVERITY_ORDER))
    shown = [r for r in detections.rows if r["severity"] in severities]

    # ---- map
    st.subheader("Map")
    layers: list[Any] = []
    if zones:
        layers.append(pdk.Layer(
            "PolygonLayer", zones, get_polygon="polygon", get_fill_color="color",
            get_line_color=[60, 60, 60, 160], line_width_min_pixels=1,
            stroked=True, pickable=True,
        ))
    if states:
        layers.append(pdk.Layer(
            "ScatterplotLayer", states, get_position=["lon", "lat"],
            get_fill_color=[120, 120, 120, 140], get_radius=250,
            radius_min_pixels=2, pickable=True,
        ))
    if shown:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            [
                {
                    **r,
                    "color": SEVERITY_COLOR.get(r["severity"], [0, 0, 0, 200]),
                    "label": (
                        f"{r['severity']} {r['anomaly_score']:.3f}<br/>"
                        f"{r['aircraft']} in {r['zone_id']}<br/>"
                        f"{_alt_label(r['altitude_ft'])}"
                    ),
                }
                for r in shown
            ],
            get_position=["lon", "lat"], get_fill_color="color",
            get_line_color=[255, 255, 255], stroked=True, line_width_min_pixels=1,
            get_radius=600, radius_min_pixels=6, pickable=True,
        ))
    center = _map_center(shown, states, zones)
    if layers:
        st.pydeck_chart(pdk.Deck(
            layers=layers,
            initial_view_state=pdk.ViewState(
                latitude=center[0], longitude=center[1], zoom=8
            ),
            tooltip={"html": "{label}"},
            map_style=None,
        ))
        st.caption(
            "Shaded areas: zones (red prohibited, orange restricted, purple TFR, blue MOA). "
            "Grey dots: aircraft positions. Large dots: detections, colored by severity."
        )
    else:
        st.info(
            f"Nothing to draw: no zones at `{airspace_path}` and no states at `{states_path}`."
        )

    # ---- detections table and detail
    left, right = st.columns([3, 2])
    with left:
        st.subheader("Detections")
        if shown:
            table = pd.DataFrame(shown)[[
                "anomaly_score", "severity", "aircraft", "zone_id", "observed_at",
                "altitude_ft", "penetration_nm", "confidence",
            ]]
            st.dataframe(table, hide_index=True, width="stretch")
        elif detections.rows:
            st.caption("No detections match the severity filter.")
        else:
            st.caption("No detections.")

    with right:
        st.subheader("Detail")
        if shown:
            labels = [
                f"{r['severity']}  {r['anomaly_score']:.3f}  {r['aircraft']} in {r['zone_id']}"
                for r in shown
            ]
            pick = st.selectbox("Detection", range(len(shown)), format_func=labels.__getitem__)
            row = shown[pick]
            st.markdown("**Why it fired**")
            for fact in row["explanation_facts"]:
                st.markdown(f"- {fact}")
            st.markdown("**What the detector could not check**")
            if row["limitations"]:
                for limit in row["limitations"]:
                    st.markdown(f"- {limit}")
            else:
                st.markdown("- None reported.")
            st.caption(f"Source record: `{row['source_row_id']}` at {row['observed_at']}")
        else:
            st.caption("Select a detection to see its explanation.")

    # ---- exit reasons
    st.subheader("Why states dropped out")
    if exit_summary and exit_summary.get("pipeline_ran") is False:
        st.warning(
            "The last CLI run did not get through the pipeline (a stage is still "
            "TODO), so no states were evaluated. Check the CLI's stage table."
        )
    elif exit_summary and exit_summary.get("exits"):
        exit_rows = sorted(
            ((str(reason), int(n)) for reason, n in exit_summary["exits"].items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        exits = pd.DataFrame(exit_rows, columns=["exit_reason", "states"]).set_index(
            "exit_reason"
        )
        st.bar_chart(exits, horizontal=True)
    elif exit_summary:
        st.caption("Every evaluated state produced a detection.")
    else:
        st.caption(
            f"No `exit_reasons.json` in `{out_dir}`. It is written by the CLI alongside "
            "the detections."
        )


def _map_center(
    shown: list[dict[str, Any]],
    states: list[dict[str, Any]] | None,
    zones: list[dict[str, Any]] | None,
) -> tuple[float, float]:
    """Center on detections, else aircraft, else zones, else KLYH."""
    if shown:
        pts = [(r["lat"], r["lon"]) for r in shown]
    elif states:
        pts = [(p["lat"], p["lon"]) for p in states]
    elif zones:
        pts = [(lat, lon) for z in zones for lon, lat in z["polygon"]]
    else:
        return (37.3267, -79.2004)
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


if __name__ == "__main__":
    main()
