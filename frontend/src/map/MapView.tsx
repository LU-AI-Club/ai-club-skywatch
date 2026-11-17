// The shared map. It owns the base map, the dark tiles, and the live aircraft
// layer (fed by the one shared observations timer). It then hands the raw
// Leaflet map to its children via context, so a team can render <MapView> and
// drop in their own layers with useLeafletMap() — no plugin framework, maximum
// flexibility.
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { config } from "../config";
import { useObservations } from "../api/observations";
import { MapContext } from "./mapContext";
import type { AircraftFeature } from "../api/types";

// Fresh fixes are bright, older ones fade toward gray.
function aircraftColor(ageHours: number): string {
  if (!Number.isFinite(ageHours)) return "#64748b";
  if (ageHours <= 0.1) return "#22d3ee";
  if (ageHours <= 1) return "#38bdf8";
  return "#64748b";
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function popupHtml(p: AircraftFeature["properties"]): string {
  const num = (v: number | null, suffix: string) =>
    typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(1)}${suffix}` : "—";
  return `
    <div style="font-weight:600;margin-bottom:4px">${escapeHtml(p.callsign || p.icao24)}</div>
    <div style="color:#9a9aa5">
      ICAO: ${escapeHtml(p.icao24)}<br/>
      Alt: ${escapeHtml(p.altitude ?? "—")}<br/>
      Speed: ${num(p.sog, " kn")}<br/>
      Track: ${num(p.cog, "°")}<br/>
      Age: ${num(p.position_age_hours, " h")}
    </div>`;
}

export interface MapViewProps {
  // Draw the shared aircraft layer. Set false if a team wants a clean canvas.
  showAircraft?: boolean;
  // Called once with the raw Leaflet map when it is ready.
  onReady?: (map: L.Map) => void;
  style?: CSSProperties;
  children?: ReactNode;
}

export function MapView({ showAircraft = true, onReady, style, children }: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
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
    layerRef.current = L.layerGroup().addTo(m);
    mapRef.current = m;
    setMap(m);
    onReady?.(m);
    return () => {
      m.remove();
      mapRef.current = null;
      layerRef.current = null;
      setMap(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Redraw the aircraft layer whenever the shared feed updates.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    layer.clearLayers();
    if (!showAircraft) return;
    for (const f of aircraft) {
      const [lon, lat] = f.geometry.coordinates;
      L.circleMarker([lat, lon], {
        radius: 5,
        color: "#0a0a0c",
        weight: 1,
        fillColor: aircraftColor(f.properties.position_age_hours),
        fillOpacity: 0.95,
      })
        .bindPopup(popupHtml(f.properties))
        .addTo(layer);
    }
  }, [aircraft, showAircraft]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", ...style }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <MapContext.Provider value={map}>{children}</MapContext.Provider>
    </div>
  );
}
