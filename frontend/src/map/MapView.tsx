// The shared map. It owns the base map, the dark tiles, the live aircraft layer
// (icons by type, rotated to face their track) and each aircraft's fading trail
// (tinted by type). All of it is fed by the one shared observations timer. It
// then hands the raw Leaflet map to its children via context, so a team can
// render <MapView> and drop in their own layers with useLeafletMap().
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { config } from "../config";
import { useObservations } from "../api/observations";
import { MapContext } from "./mapContext";
import type { AircraftFeature } from "../api/types";

// --- Aircraft type, from the ADS-B emitter category ------------------------
// A1/A2 = light, A3/A4/A5 = large, A7 = rotorcraft; everything else (incl. no
// category, gliders, drones, ground vehicles) is "unknown".
type AircraftKind = "passenger" | "private" | "helicopter" | "unknown";

function aircraftKind(category: string | null): AircraftKind {
  switch (category) {
    case "A3":
    case "A4":
    case "A5":
      return "passenger";
    case "A1":
    case "A2":
      return "private";
    case "A7":
      return "helicopter";
    default:
      return "unknown";
  }
}

const KIND_LABEL: Record<AircraftKind, string> = {
  passenger: "Passenger",
  private: "Private",
  helicopter: "Helicopter",
  unknown: "Unknown",
};

const KIND_COLOR: Record<AircraftKind, string> = {
  passenger: "#38bdf8", // sky blue
  private: "#facc15", // gold
  helicopter: "#f472b6", // pink
  unknown: "#94a3b8", // slate
};

// Each icon points "up" (north) at 0°, so rotating by the track (cog) makes it
// face its direction of travel. Built once per kind with the color baked in.
const STROKE = '#0a0a0c" stroke-width="0.7';
const PLANE_PATH =
  "M12 2 C11.2 2 10.6 2.6 10.6 3.4 V9 L2 14 V15.8 L10.6 13.3 V18.6 L8.2 20.2 V21.6 L12 20.6 L15.8 21.6 V20.2 L13.4 18.6 V13.3 L22 15.8 V14 L13.4 9 V3.4 C13.4 2.6 12.8 2 12 2 Z";

function planeSvg(color: string, size: number): string {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" style="display:block"><path fill="${color}" stroke="${STROKE}" d="${PLANE_PATH}"/></svg>`;
}

const KIND_ICON: Record<AircraftKind, { size: number; svg: string }> = {
  passenger: { size: 22, svg: planeSvg(KIND_COLOR.passenger, 22) },
  private: { size: 16, svg: planeSvg(KIND_COLOR.private, 16) },
  helicopter: {
    size: 20,
    svg: `<svg viewBox="0 0 24 24" width="20" height="20" style="display:block">
      <line x1="12" y1="3" x2="12" y2="21.5" stroke="${KIND_COLOR.helicopter}" stroke-width="1.3"/>
      <ellipse cx="12" cy="11" rx="2.8" ry="4.6" fill="${KIND_COLOR.helicopter}" stroke="${STROKE}"/>
      <line x1="3.5" y1="7.3" x2="20.5" y2="7.3" stroke="${KIND_COLOR.helicopter}" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="12" y1="2.3" x2="12" y2="14" stroke="${KIND_COLOR.helicopter}" stroke-width="1.5" stroke-linecap="round"/>
      <line x1="9.6" y1="21.3" x2="14.4" y2="21.3" stroke="${KIND_COLOR.helicopter}" stroke-width="1.3" stroke-linecap="round"/>
    </svg>`,
  },
  unknown: {
    size: 13,
    svg: `<svg viewBox="0 0 24 24" width="13" height="13" style="display:block"><path fill="${KIND_COLOR.unknown}" stroke="${STROKE}" d="M12 3 L20 20 L12 15.5 L4 20 Z"/></svg>`,
  },
};

function aircraftIcon(kind: AircraftKind, cog: number | null): L.DivIcon {
  const { size, svg } = KIND_ICON[kind];
  const rot = typeof cog === "number" && Number.isFinite(cog) ? cog : 0;
  return L.divIcon({
    className: "aircraft-marker",
    html: `<div style="transform:rotate(${rot}deg);transform-origin:center;line-height:0">${svg}</div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

// --- Trail tuning -----------------------------------------------------------
// A trail is built from the aircraft's recent positions (one point per refresh),
// tinted by the aircraft's type, fading with age so it thins out behind the
// plane and is gone by TRAIL_MAX_AGE_MS. Visible but not distracting.
const TRAIL_MAX_AGE_MS = 180_000; // 3 minutes, then the point drops off
const TRAIL_MAX_OPACITY = 0.55; // freshest segment, right behind the plane
const TRAIL_MIN_OPACITY = 0.05; // oldest segment, about to disappear
const TRAIL_WEIGHT = 1.5; // px
const TRAIL_MAX_POINTS = 48; // safety cap (age-out normally keeps it far smaller)

interface TrailPoint {
  lat: number;
  lon: number;
  t: number; // client time this point was recorded
}
interface Trail {
  color: string; // tint, from the aircraft's type
  points: TrailPoint[];
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function popupHtml(p: AircraftFeature["properties"], kind: AircraftKind): string {
  const num = (v: number | null, suffix: string) =>
    typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(1)}${suffix}` : "—";
  return `
    <div style="font-weight:600;margin-bottom:4px">${escapeHtml(p.callsign || p.icao24)}</div>
    <div style="color:#9a9aa5">
      Type: <span style="color:${KIND_COLOR[kind]}">${KIND_LABEL[kind]}</span>${p.category ? ` (${escapeHtml(p.category)})` : ""}<br/>
      ICAO: ${escapeHtml(p.icao24)}<br/>
      Alt: ${escapeHtml(p.altitude ?? "—")}<br/>
      Speed: ${num(p.sog, " kn")}<br/>
      Track: ${num(p.cog, "°")}<br/>
      Age: ${num(p.position_age_hours, " h")}
    </div>`;
}

export interface MapViewProps {
  // Draw the shared aircraft layer (icons + trails). Set false for a clean canvas.
  showAircraft?: boolean;
  // Show the aircraft-type legend in the corner.
  showLegend?: boolean;
  // Called once with the raw Leaflet map when it is ready.
  onReady?: (map: L.Map) => void;
  style?: CSSProperties;
  children?: ReactNode;
}

export function MapView({
  showAircraft = true,
  showLegend = true,
  onReady,
  style,
  children,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const trailLayerRef = useRef<L.LayerGroup | null>(null);
  const trailRendererRef = useRef<L.Canvas | null>(null);
  // icao hex -> recent positions + tint. Lives across renders; never React state.
  const trailsRef = useRef<Map<string, Trail>>(new Map());
  const [map, setMap] = useState<L.Map | null>(null);
  const { aircraft } = useObservations();

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const m = L.map(containerRef.current, {
      center: config.mapCenter,
      zoom: config.mapZoom,
      zoomControl: true,
    });
    L.tileLayer(config.tileUrl, {
      attribution: config.tileAttribution,
      maxZoom: 19,
    }).addTo(m);

    // Trails render on a canvas in their own pane, kept BELOW the aircraft
    // markers (marker pane) so a plane is never hidden by a line.
    m.createPane("trails");
    const trailPane = m.getPane("trails");
    if (trailPane) trailPane.style.zIndex = "350";
    trailRendererRef.current = L.canvas({ pane: "trails", padding: 0.5 });
    trailLayerRef.current = L.layerGroup().addTo(m);

    layerRef.current = L.layerGroup().addTo(m);
    mapRef.current = m;
    setMap(m);
    onReady?.(m);
    return () => {
      m.remove();
      mapRef.current = null;
      layerRef.current = null;
      trailLayerRef.current = null;
      trailRendererRef.current = null;
      trailsRef.current.clear();
      setMap(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // On every shared-feed update: extend each trail, age old points out, and
  // redraw both the trails and the aircraft icons.
  useEffect(() => {
    const layer = layerRef.current;
    const trailLayer = trailLayerRef.current;
    const renderer = trailRendererRef.current;
    if (!layer || !trailLayer) return;

    const now = Date.now();
    const trails = trailsRef.current;

    layer.clearLayers();
    trailLayer.clearLayers();

    if (!showAircraft) {
      trails.clear();
      return;
    }

    // 1. Append each aircraft's latest position (only when it moved), and keep
    //    its tint current.
    for (const f of aircraft) {
      const [lon, lat] = f.geometry.coordinates;
      const kind = aircraftKind(f.properties.category);
      let trail = trails.get(f.id);
      if (!trail) {
        trail = { color: KIND_COLOR[kind], points: [] };
        trails.set(f.id, trail);
      }
      trail.color = KIND_COLOR[kind];
      const last = trail.points[trail.points.length - 1];
      if (!last || last.lat !== lat || last.lon !== lon) {
        trail.points.push({ lat, lon, t: now });
        if (trail.points.length > TRAIL_MAX_POINTS) trail.points.shift();
      }
    }

    // 2. Drop points past the fade window; forget aircraft with nothing left.
    for (const [id, trail] of trails) {
      while (trail.points.length && now - trail.points[0].t > TRAIL_MAX_AGE_MS) {
        trail.points.shift();
      }
      if (trail.points.length === 0) trails.delete(id);
    }

    // 3. Draw each trail as segments that fade with age, tinted by type.
    for (const trail of trails.values()) {
      const pts = trail.points;
      for (let i = 1; i < pts.length; i++) {
        const a = pts[i - 1];
        const b = pts[i];
        const frac = Math.max(0, 1 - (now - b.t) / TRAIL_MAX_AGE_MS); // 1 fresh -> 0 old
        const opacity = TRAIL_MIN_OPACITY + (TRAIL_MAX_OPACITY - TRAIL_MIN_OPACITY) * frac;
        L.polyline(
          [
            [a.lat, a.lon],
            [b.lat, b.lon],
          ],
          {
            color: trail.color,
            weight: TRAIL_WEIGHT,
            opacity,
            interactive: false,
            ...(renderer ? { renderer } : {}),
          },
        ).addTo(trailLayer);
      }
    }

    // 4. Draw the aircraft icons on top, each rotated to face its track.
    for (const f of aircraft) {
      const [lon, lat] = f.geometry.coordinates;
      const kind = aircraftKind(f.properties.category);
      L.marker([lat, lon], { icon: aircraftIcon(kind, f.properties.cog) })
        .bindPopup(popupHtml(f.properties, kind))
        .addTo(layer);
    }
  }, [aircraft, showAircraft]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", ...style }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      {showLegend && showAircraft && (
        <div
          style={{
            position: "absolute",
            left: 12,
            bottom: 14,
            zIndex: 900,
            background: "rgba(20,20,24,0.94)",
            border: "1px solid #2a2a32",
            borderRadius: 8,
            padding: "8px 11px",
            font: "12px system-ui, sans-serif",
            color: "#f4f4f6",
            display: "grid",
            gap: 5,
          }}
        >
          {(Object.keys(KIND_LABEL) as AircraftKind[]).map((k) => (
            <span key={k} style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span
                style={{
                  width: 10,
                  height: 10,
                  borderRadius: 2,
                  background: KIND_COLOR[k],
                  display: "inline-block",
                }}
              />
              {KIND_LABEL[k]}
            </span>
          ))}
        </div>
      )}
      <MapContext.Provider value={map}>{children}</MapContext.Provider>
    </div>
  );
}
