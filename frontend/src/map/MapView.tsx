// The shared map. It owns the base map, the dark tiles, and the live aircraft
// layer (fed by the one shared observations timer). It then hands the raw
// Leaflet map to its children via context, so a team can render <MapView> and
// drop in their own layers with useLeafletMap() — no plugin framework, maximum
// flexibility.
import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import { config } from "../config";
import { useObservations } from "../api/observations";
import { fetchTrack } from "../api/tracks";
import { aircraftTypeInfo, aircraftTypeLabel, classifyAircraft } from "../api/aircraftType";
import { MapContext } from "./mapContext";
import type { AircraftFeature } from "../api/types";

// The full extent of Web Mercator tiles (latitude is capped at ±85.05°).
const WORLD_BOUNDS = L.latLngBounds([-85.0511, -180], [85.0511, 180]);

// Fresh fixes are bright, older ones fade toward gray.
// Color says what kind of aircraft it is; fading says how old the position is.
function aircraftOpacity(ageHours: number): number {
  if (!Number.isFinite(ageHours)) return 0.4;
  if (ageHours <= 0.1) return 1;
  if (ageHours <= 1) return 0.7;
  return 0.4;
}

// Top-down plane silhouette pointing straight up (north, 0°), so rotating it by
// the compass heading points it the right way. Path from Material Icons
// "flight" (Apache 2.0); the viewBox centers the fuselage on the marker.
export const PLANE_PATH =
  "M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z";
const PLANE_SIZE = 22;
const PLANE_ICON = L.divIcon({
  className: "aircraft-marker",
  html: `<svg class="aircraft-plane" viewBox="0 0 23 24" width="${PLANE_SIZE}" height="${PLANE_SIZE}" aria-hidden="true">
    <path d="${PLANE_PATH}"/>
  </svg>`,
  iconSize: [PLANE_SIZE, PLANE_SIZE],
  iconAnchor: [PLANE_SIZE / 2, PLANE_SIZE / 2],
  popupAnchor: [0, -PLANE_SIZE / 2],
});

// Which way the nose points: true heading if reported, else course over ground.
function aircraftRotation(p: AircraftFeature["properties"]): number {
  for (const v of [p.heading, p.cog]) {
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return 0;
}

// Rotate and color the plane in place. The marker's own element is positioned
// by Leaflet with a transform, so the rotation goes on the inner <svg>.
function stylePlane(marker: L.Marker, rotationDeg: number, color: string, opacity: number): void {
  const svg = marker.getElement()?.querySelector<SVGElement>(".aircraft-plane");
  if (!svg) return;
  svg.style.transform = `rotate(${rotationDeg}deg)`;
  svg.style.fill = color;
  svg.style.opacity = String(opacity);
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
      Type: ${escapeHtml(aircraftTypeLabel(classifyAircraft(p)))}${p.category ? ` (${escapeHtml(p.category)})` : ""}<br/>
      Alt: ${escapeHtml(p.altitude ?? "—")}<br/>
      Speed: ${num(p.sog, " kn")}<br/>
      Track: ${num(p.cog, "°")}<br/>
      Age: ${num(p.position_age_hours, " h")}
    </div>`;
}

export interface MapViewProps {
  // Draw the shared aircraft layer. Set false if a team wants a clean canvas.
  showAircraft?: boolean;
  // Show only aircraft this returns true for (e.g. a type filter). Pass a
  // stable function (useCallback) so the layer only resyncs when it changes.
  filterAircraft?: (aircraft: AircraftFeature) => boolean;
  // Called once with the raw Leaflet map when it is ready.
  onReady?: (map: L.Map) => void;
  style?: CSSProperties;
  children?: ReactNode;
}

// Imperative handle for pages that drive the map from outside it (e.g. a search
// box in a sidebar): <MapView ref={ref}> then ref.current?.focusAircraft(icao).
export interface MapViewHandle {
  // Zoom to an aircraft and open its popup. Returns false if it isn't on the map.
  focusAircraft: (icao24: string) => boolean;
  // The raw Leaflet map, or null before it mounts.
  getMap: () => L.Map | null;
}

// Zoom level used when jumping to a single aircraft.
const FOCUS_ZOOM = 11;

// The selected aircraft's path: a bright line over a dark casing so it reads on
// any basemap, plus a dot where the path starts.
const TRACK_COLOR = "#f472b6";
const TRACK_STYLE: L.PolylineOptions = { color: TRACK_COLOR, weight: 2.5, opacity: 0.95, interactive: false };
const TRACK_CASING: L.PolylineOptions = { color: "#0a0a0c", weight: 6, opacity: 0.55, interactive: false };

function sameSpot(a: L.LatLng, b: L.LatLng): boolean {
  return Math.abs(a.lat - b.lat) < 1e-7 && Math.abs(a.lng - b.lng) < 1e-7;
}

export const MapView = forwardRef<MapViewHandle, MapViewProps>(function MapView(
  { showAircraft = true, filterAircraft, onReady, style, children },
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const markersRef = useRef(new Map<string, L.Marker>());
  const trackLayerRef = useRef<L.LayerGroup | null>(null);
  const trackLinesRef = useRef<L.Polyline[]>([]);
  // The aircraft whose popup is open; its path is drawn on the map.
  const [selected, setSelected] = useState<string | null>(null);
  const [map, setMap] = useState<L.Map | null>(null);
  const { aircraft } = useObservations();

  useImperativeHandle(
    ref,
    () => ({
      focusAircraft(icao24) {
        const m = mapRef.current;
        const marker = markersRef.current.get(icao24);
        if (!m || !marker) return false;
        const zoom = Math.max(m.getZoom(), FOCUS_ZOOM);
        m.flyTo(marker.getLatLng(), zoom, { duration: 0.8 });
        // Open after the flight so the popup isn't panned around mid-animation.
        m.once("moveend", () => marker.openPopup());
        return true;
      },
      getMap: () => mapRef.current,
    }),
    [],
  );

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const m = L.map(containerRef.current, {
      center: config.mapCenter,
      zoom: config.mapZoom,
      zoomControl: true,
      // Show exactly one world: no side-by-side copies when zoomed out, and
      // panning stops hard at the edges instead of drifting into empty space.
      maxBounds: WORLD_BOUNDS,
      maxBoundsViscosity: 1.0,
    });
    L.tileLayer(config.tileUrl, {
      attribution: config.tileAttribution,
      maxZoom: 19,
      noWrap: true,
      bounds: WORLD_BOUNDS,
    }).addTo(m);

    // Don't let the user zoom out past the point where the world fills the
    // viewport, otherwise gray bars appear around the single world copy.
    // Depends on container size, so recompute on resize.
    const fitMinZoom = () => {
      const z = m.getBoundsZoom(WORLD_BOUNDS, true);
      m.setMinZoom(Math.max(0, Math.ceil(z)));
    };
    fitMinZoom();
    m.on("resize", fitMinZoom);

    // Path layer first, so it sits under the aircraft markers.
    trackLayerRef.current = L.layerGroup().addTo(m);
    layerRef.current = L.layerGroup().addTo(m);
    mapRef.current = m;
    setMap(m);
    onReady?.(m);
    return () => {
      m.off("resize", fitMinZoom);
      m.remove();
      mapRef.current = null;
      layerRef.current = null;
      trackLayerRef.current = null;
      trackLinesRef.current = [];
      markersRef.current.clear();
      setMap(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Sync the aircraft layer with the shared feed. Markers are kept per ICAO and
  // moved in place rather than rebuilt, so an open popup survives each update.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) return;
    const markers = markersRef.current;
    if (!showAircraft) {
      layer.clearLayers();
      markers.clear();
      return;
    }
    const seen = new Set<string>();
    for (const f of aircraft) {
      if (filterAircraft && !filterAircraft(f)) continue;
      const id = f.properties.icao24 || f.id;
      const [lon, lat] = f.geometry.coordinates;
      const fillColor = aircraftTypeInfo(classifyAircraft(f.properties)).color;
      const opacity = aircraftOpacity(f.properties.position_age_hours);
      const html = popupHtml(f.properties);
      seen.add(id);
      const rotation = aircraftRotation(f.properties);
      const existing = markers.get(id);
      if (existing) {
        existing.setLatLng([lat, lon]);
        existing.setPopupContent(html);
        stylePlane(existing, rotation, fillColor, opacity);
      } else {
        const marker = L.marker([lat, lon], { icon: PLANE_ICON, keyboard: false })
          .bindPopup(html)
          .on("popupopen", () => setSelected(id))
          .on("popupclose", () => setSelected((cur) => (cur === id ? null : cur)))
          .addTo(layer);
        stylePlane(marker, rotation, fillColor, opacity);
        markers.set(id, marker);
      }
    }
    for (const [id, marker] of markers) {
      if (!seen.has(id)) {
        marker.remove();
        markers.delete(id);
      }
    }

    // Keep the selected aircraft's path growing as it moves.
    const selectedMarker = selected ? markers.get(selected) : undefined;
    if (selectedMarker) {
      const pos = selectedMarker.getLatLng();
      for (const line of trackLinesRef.current) {
        const pts = line.getLatLngs() as L.LatLng[];
        if (!pts.length || !sameSpot(pts[pts.length - 1], pos)) line.addLatLng(pos);
      }
    }
    // `selected` is read for the live extension only; selection changes are
    // handled by the path effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aircraft, showAircraft, filterAircraft]);

  // Draw the selected aircraft's path; clear it when the popup closes.
  useEffect(() => {
    const layer = trackLayerRef.current;
    if (!layer || !selected) return;
    const controller = new AbortController();

    fetchTrack(selected, controller.signal)
      .then((points) => {
        if (controller.signal.aborted) return;
        const latlngs = points.map((p) => L.latLng(p.lat, p.lon));
        // End the path at the plane's current spot, which may be newer.
        const current = markersRef.current.get(selected)?.getLatLng();
        if (current && (!latlngs.length || !sameSpot(latlngs[latlngs.length - 1], current))) {
          latlngs.push(current);
        }
        if (latlngs.length < 2) return;
        const casing = L.polyline(latlngs, TRACK_CASING).addTo(layer);
        const line = L.polyline(latlngs, TRACK_STYLE).addTo(layer);
        trackLinesRef.current = [casing, line];
        const first = points[0];
        L.circleMarker(latlngs[0], {
          radius: 4,
          color: "#0a0a0c",
          weight: 1.5,
          fillColor: TRACK_COLOR,
          fillOpacity: 1,
        })
          .bindTooltip(
            first ? `First seen ${new Date(first.observedAt).toLocaleTimeString()}` : "Start",
            { direction: "top", offset: [0, -4] },
          )
          .addTo(layer);
      })
      .catch((err) => {
        if ((err as Error).name !== "AbortError") {
          console.warn(`Couldn't load path for ${selected}:`, err);
        }
      });

    return () => {
      controller.abort();
      layer.clearLayers();
      trackLinesRef.current = [];
    };
  }, [selected, map]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%", ...style }}>
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />
      <MapContext.Provider value={map}>{children}</MapContext.Provider>
    </div>
  );
});
