// 3D airspace view for the no-fly-zone page (MapLibre GL, no API key).
//
//   - Zones are extruded from their floor to their ceiling altitude.
//   - Live aircraft are arrows at their reported altitude, pointed along their
//     heading, with a thin stem down to the ground. Red = inside a zone volume.
//   - Incursions are diamonds at the altitude the detector recorded.
//
// Heights are multiplied by a vertical exaggeration (slider) because airspace is
// far wider than it is tall: at 1x an 18,000 ft ceiling over a 40 nm MOA looks flat.
//
// Approximation: AGL floors/ceilings are drawn as MSL + GROUND_FT (a typical
// terrain height around KLYH). The detector itself uses real terrain; this view
// is for orientation only.
import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type GeoJSONSource, type Map as MlMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { config } from "../../config";
import { useObservations } from "../../api/observations";
import type { AircraftFeature, Detection } from "../../api/types";
import {
  ZONE_TYPES,
  escapeHtml,
  meta,
  zoneColor,
  zoneIdOf,
  zoneNameOf,
  type ZoneFeature,
  type ZoneProperties,
} from "./zones";

const FT_TO_M = 0.3048;
const GROUND_FT = 900;
const SEV_COLORS: Record<string, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#f59e0b",
  low: "#10b981",
  info: "#3b82f6",
};

type Geo = GeoJSON.Feature<GeoJSON.Polygon | GeoJSON.MultiPolygon, Record<string, unknown>>;
const fc = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({
  type: "FeatureCollection",
  features,
});

// ---- altitude helpers ----------------------------------------------------------

function boundFt(ft: number | undefined, datum: string | undefined): number {
  if (datum === "SFC" || ft == null) return 0;
  return datum === "AGL" ? ft + GROUND_FT : ft;
}
const floorFt = (p: ZoneProperties) => boundFt(p.floor_ft, p.floor_datum);
const ceilingFt = (p: ZoneProperties) => boundFt(p.ceiling_ft ?? 18000, p.ceiling_datum);

function aircraftAltFt(a: AircraftFeature): number | null {
  const raw = a.properties.altitude;
  if (raw == null || String(raw).toLowerCase() === "ground") return 0;
  const n = parseFloat(String(raw));
  return Number.isFinite(n) ? n : null;
}

// ---- geometry helpers ----------------------------------------------------------

function ringContains(ring: number[][], lon: number, lat: number): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function geomContains(g: GeoJSON.Geometry, lon: number, lat: number): boolean {
  const poly = (rings: number[][][]) =>
    ringContains(rings[0], lon, lat) && !rings.slice(1).some((h) => ringContains(h, lon, lat));
  if (g.type === "Polygon") return poly(g.coordinates);
  if (g.type === "MultiPolygon") return g.coordinates.some(poly);
  return false;
}

// A polygon from local (east, north) metre offsets around a point, rotated by heading.
function localPolygon(lon: number, lat: number, pts: [number, number][], headingDeg = 0) {
  const h = (headingDeg * Math.PI) / 180;
  const mPerDegLat = 111320;
  const mPerDegLon = 111320 * Math.cos((lat * Math.PI) / 180);
  const ring = pts.map(([x, y]) => {
    const east = x * Math.cos(h) + y * Math.sin(h);
    const north = -x * Math.sin(h) + y * Math.cos(h);
    return [lon + east / mPerDegLon, lat + north / mPerDegLat];
  });
  ring.push(ring[0]);
  return { type: "Polygon" as const, coordinates: [ring] };
}

const ARROW: [number, number][] = [
  [0, 900],
  [-550, -600],
  [0, -250],
  [550, -600],
];
const square = (r: number): [number, number][] => [
  [-r, -r],
  [r, -r],
  [r, r],
  [-r, r],
];
const diamond = (r: number): [number, number][] => [
  [0, r],
  [r, 0],
  [0, -r],
  [-r, 0],
];

function bboxOf(g: GeoJSON.Geometry): [[number, number], [number, number]] | null {
  let minX = Infinity,
    minY = Infinity,
    maxX = -Infinity,
    maxY = -Infinity;
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") {
      const [x, y] = c as number[];
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
    } else if (Array.isArray(c)) c.forEach(walk);
  };
  if ("coordinates" in g) walk(g.coordinates);
  return Number.isFinite(minX) ? [[minX, minY], [maxX, maxY]] : null;
}

// ---- component -----------------------------------------------------------------

export function Nfz3DMap({
  zones,
  detections,
  showAircraft,
  selectedZone,
  selectedId,
  onSelectZone,
  onSelect,
}: {
  zones: ZoneFeature[];
  detections: Detection[];
  showAircraft: boolean;
  selectedZone: string | null;
  selectedId: string | null;
  onSelectZone: (zoneId: string | null) => void;
  onSelect: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MlMap | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const [ready, setReady] = useState(false);
  const [exag, setExag] = useState(4);
  const [zoom, setZoom] = useState(config.mapZoom - 0.7);
  // Plane arrows are sized in metres, so grow them when zoomed out to stay visible.
  const planeScale = Math.min(5, Math.max(0.5, 2 ** (10 - zoom)));
  const { aircraft } = useObservations();

  const cb = useRef({ onSelectZone, onSelect });
  cb.current = { onSelectZone, onSelect };

  // ---- derived GeoJSON ----------------------------------------------------------

  const zoneData = useMemo(
    () =>
      fc(
        zones.map(
          (z): Geo => ({
            type: "Feature",
            geometry: z.geometry as Geo["geometry"],
            properties: {
              zone_id: z.properties.zone_id,
              color: zoneColor(z.properties.zone_type),
              selected: z.properties.zone_id === selectedZone,
              base: floorFt(z.properties) * FT_TO_M * exag,
              top: ceilingFt(z.properties) * FT_TO_M * exag,
            },
          }),
        ),
      ),
    [zones, selectedZone, exag],
  );

  const { planes, stems, insideCount } = useMemo(() => {
    const planes: GeoJSON.Feature[] = [];
    const stems: GeoJSON.Feature[] = [];
    let insideCount = 0;
    if (!showAircraft) return { planes, stems, insideCount };
    for (const a of aircraft) {
      const [lon, lat] = a.geometry.coordinates;
      const alt = aircraftAltFt(a);
      if (alt == null) continue;
      const inZone = zones.find(
        (z) =>
          alt >= floorFt(z.properties) &&
          alt <= ceilingFt(z.properties) &&
          geomContains(z.geometry, lon, lat),
      );
      if (inZone) insideCount++;
      const stale = a.properties.position_age_hours > 0.1;
      const color = inZone ? "#ef4444" : stale ? "#64748b" : "#22d3ee";
      const base = alt * FT_TO_M * exag;
      const props = {
        icao24: a.properties.icao24,
        callsign: a.properties.callsign ?? "",
        alt,
        speed: a.properties.sog,
        zone: inZone?.properties.zone_id ?? "",
        color,
      };
      planes.push({
        type: "Feature",
        geometry: localPolygon(
          lon,
          lat,
          ARROW.map(([x, y]) => [x * planeScale, y * planeScale] as [number, number]),
          a.properties.heading ?? a.properties.cog ?? 0,
        ),
        properties: { ...props, base, top: base + 220 * planeScale },
      });
      if (alt > 0) {
        stems.push({
          type: "Feature",
          geometry: localPolygon(lon, lat, square(45 * planeScale)),
          properties: { color, base: 0, top: base },
        });
      }
    }
    return { planes, stems, insideCount };
  }, [aircraft, zones, showAircraft, exag, planeScale]);

  const incursionData = useMemo(() => {
    const out: GeoJSON.Feature[] = [];
    for (const d of detections) {
      if (typeof d.latitude !== "number" || typeof d.longitude !== "number") continue;
      const altFt = meta(d).extras?.altitude_ft;
      const alt = typeof altFt === "number" ? altFt : 0;
      const base = alt * FT_TO_M * exag;
      const selected = d.detection_id === selectedId;
      out.push({
        type: "Feature",
        geometry: localPolygon(d.longitude, d.latitude, diamond(selected ? 900 : 600)),
        properties: {
          detection_id: d.detection_id,
          color: selected ? "#ffffff" : (SEV_COLORS[String(d.severity).toLowerCase()] ?? "#94a3b8"),
          base,
          top: base + (selected ? 500 : 350),
        },
      });
    }
    return fc(out);
  }, [detections, selectedId, exag]);

  // ---- map setup (once) ---------------------------------------------------------

  useEffect(() => {
    if (!containerRef.current) return;
    const [lat, lon] = config.mapCenter;
    const map = new maplibregl.Map({
      container: containerRef.current,
      center: [lon, lat],
      zoom: config.mapZoom - 0.7,
      pitch: 60,
      bearing: -20,
      maxPitch: 85,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          base: {
            type: "raster",
            tiles: [config.tileUrl],
            tileSize: 256,
            attribution: config.tileAttribution,
          },
        },
        layers: [{ id: "base", type: "raster", source: "base" }],
      },
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    mapRef.current = map;
    map.on("zoomend", () => setZoom(map.getZoom()));

    map.on("load", () => {
      const empty = fc([]);
      for (const id of ["zones", "stems", "planes", "incursions"]) {
        map.addSource(id, { type: "geojson", data: empty });
      }
      const extrusion = (id: string, opacity: number) =>
        map.addLayer({
          id,
          source: id,
          type: "fill-extrusion",
          paint: {
            "fill-extrusion-color": ["get", "color"],
            "fill-extrusion-base": ["get", "base"],
            "fill-extrusion-height": ["get", "top"],
            "fill-extrusion-opacity": opacity,
          },
        });
      // Ground footprint so zone outlines read even at shallow pitch.
      map.addLayer({
        id: "zones-outline",
        source: "zones",
        type: "line",
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["case", ["get", "selected"], 3, 1.5],
          "line-opacity": 0.9,
        },
      });
      map.addLayer({
        id: "zones",
        source: "zones",
        type: "fill-extrusion",
        paint: {
          "fill-extrusion-color": [
            "case",
            ["get", "selected"],
            "#ffffff",
            ["get", "color"],
          ],
          "fill-extrusion-base": ["get", "base"],
          "fill-extrusion-height": ["get", "top"],
          "fill-extrusion-opacity": 0.28,
        },
      });
      extrusion("stems", 0.45);
      extrusion("planes", 0.95);
      extrusion("incursions", 0.95);
      setReady(true);
    });

    // One click handler, in priority order: incursion > aircraft > zone.
    map.on("click", (e) => {
      const hit = (layer: string) =>
        map.queryRenderedFeatures(e.point, { layers: [layer] })[0] as
          | maplibregl.MapGeoJSONFeature
          | undefined;
      const inc = hit("incursions");
      if (inc) return cb.current.onSelect(String(inc.properties.detection_id));
      const plane = hit("planes");
      if (plane) {
        const p = plane.properties;
        popupRef.current?.remove();
        popupRef.current = new maplibregl.Popup({ closeButton: false, className: "nfz-popup" })
          .setLngLat(e.lngLat)
          .setHTML(
            `<b>${escapeHtml(p.callsign || p.icao24)}</b><br/>` +
              `ICAO ${escapeHtml(p.icao24)}<br/>` +
              `Alt ${Number(p.alt).toLocaleString()} ft` +
              (p.speed != null && p.speed !== "null" ? ` · ${Math.round(Number(p.speed))} kn` : "") +
              (p.zone ? `<br/><span style="color:#fca5a5">Inside ${escapeHtml(p.zone)}</span>` : ""),
          )
          .addTo(map);
        return;
      }
      const zone = hit("zones");
      if (zone) cb.current.onSelectZone(String(zone.properties.zone_id));
    });
    map.on("mousemove", (e) => {
      const hits = map.queryRenderedFeatures(e.point, {
        layers: ["incursions", "planes", "zones"].filter((l) => map.getLayer(l)),
      });
      map.getCanvas().style.cursor = hits.length ? "pointer" : "";
    });

    return () => {
      popupRef.current?.remove();
      map.remove();
      mapRef.current = null;
      setReady(false);
    };
  }, []);

  // ---- push data into the sources -----------------------------------------------

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("zones") as GeoJSONSource).setData(zoneData);
    (map.getSource("planes") as GeoJSONSource).setData(fc(planes));
    (map.getSource("stems") as GeoJSONSource).setData(fc(stems));
    (map.getSource("incursions") as GeoJSONSource).setData(incursionData);
  }, [ready, zoneData, planes, stems, incursionData]);

  // ---- fly to selection -----------------------------------------------------------

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !selectedId) return;
    const d = detections.find((x) => x.detection_id === selectedId);
    if (d && typeof d.latitude === "number" && typeof d.longitude === "number") {
      map.flyTo({
        center: [d.longitude, d.latitude],
        zoom: Math.max(map.getZoom(), 10),
        pitch: 65,
        duration: 900,
      });
    }
    // Only when the selection changes, not on every data refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !selectedZone) return;
    const z = zones.find((x) => x.properties.zone_id === selectedZone);
    const bb = z && bboxOf(z.geometry);
    if (bb) map.fitBounds(bb, { padding: 60, pitch: 60, bearing: map.getBearing(), duration: 900, maxZoom: 11 });
  }, [selectedZone, ready, zones]);

  const resetView = () => {
    const [lat, lon] = config.mapCenter;
    mapRef.current?.flyTo({
      center: [lon, lat],
      zoom: config.mapZoom - 0.7,
      pitch: 60,
      bearing: -20,
      duration: 900,
    });
  };

  const sel = selectedId ? detections.find((d) => d.detection_id === selectedId) : null;

  return (
    <div className="nfz-3d">
      <div ref={containerRef} className="nfz-3d-canvas" />
      <div className="nfz-3d-panel">
        <label>
          Height ×{exag}
          <input
            type="range"
            min={1}
            max={10}
            step={1}
            value={exag}
            onChange={(e) => setExag(Number(e.target.value))}
          />
        </label>
        <button className="nfz-link" onClick={resetView}>
          Reset view
        </button>
        {showAircraft && (
          <div className={`nfz-3d-inside ${insideCount ? "hot" : ""}`}>
            {insideCount} aircraft inside a zone volume
          </div>
        )}
        {sel && (
          <div className="nfz-muted">
            Focused: {sel.entity_id} in {zoneNameOf(sel)} ({zoneIdOf(sel)})
          </div>
        )}
      </div>
      <div className="nfz-legend">
        {ZONE_TYPES.filter((z) => zones.some((f) => f.properties.zone_type === z.type)).map((z) => (
          <span key={z.type}>
            <i style={{ background: z.color }} />
            {z.label}
          </span>
        ))}
        <span>
          <i style={{ background: "#22d3ee" }} />
          Aircraft
        </span>
        <span>
          <i style={{ background: "#ef4444" }} />
          In a zone
        </span>
        <span className="nfz-legend-note">◆ incursion · drag with right mouse / Ctrl to tilt</span>
      </div>
    </div>
  );
}
