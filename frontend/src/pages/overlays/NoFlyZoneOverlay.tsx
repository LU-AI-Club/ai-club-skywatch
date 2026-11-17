// No-fly-zone map overlay: draws the airspace polygons, highlights zones that
// have a detection, marks each incursion, and rings the matching live aircraft.
// Rendered inside <MapView>.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import { useObservations } from "../../api/observations";
import type { Detection } from "../../api/types";

const ZONE_FILES = ["/airspace/klyh-local-faa.geojson", "/airspace/klyh-demo.geojson"];
// Sectional-chart colors (match NoFlyZonePage.css): blue for prohibited and
// restricted airspace, magenta for MOAs. Leaflet needs real hex values here,
// not CSS variables.
const CHART_BLUE = "#4f8bff";
const CHART_MAGENTA = "#e040fb";
function zoneColor(type: unknown): string {
  return String(type ?? "").toUpperCase() === "MOA" ? CHART_MAGENTA : CHART_BLUE;
}
// Shared severity scale (same values as --sev-* in theme.css).
const SEVERITY: Record<string, string> = {
  info: "#3b82f6",
  low: "#10b981",
  medium: "#f59e0b",
  high: "#f97316",
  critical: "#ef4444",
};
function severityColor(sev: unknown): string {
  return SEVERITY[String(sev ?? "").toLowerCase()] ?? "#64748b";
}

type ZoneCollection = { type: string; features: unknown[] };

function esc(v: unknown): string {
  return String(v ?? "—").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

export function NoFlyZoneOverlay({
  detections,
  selectedId,
  preferLive = true,
}: {
  detections: Detection[];
  selectedId?: string | null;
  // true: ring the aircraft where it is now (falls back to the detection point).
  // false: always mark where the incursion was detected.
  preferLive?: boolean;
}) {
  const map = useLeafletMap();
  const { aircraft } = useObservations();
  const [zones, setZones] = useState<ZoneCollection[]>([]);

  // Zone polygons are static: fetch once.
  useEffect(() => {
    let cancelled = false;
    Promise.all(ZONE_FILES.map((f) => fetch(f).then((r) => r.json() as Promise<ZoneCollection>)))
      .then((z) => !cancelled && setZones(z))
      .catch(() => !cancelled && setZones([]));
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    const hotZones = new Set(detections.map((d) => String(d.zone_id ?? "")));

    for (const fc of zones) {
      // Chart-style "hatched" border: a wide dotted stroke under the outline
      // reads as the tick marks sectional charts draw inside restricted areas.
      L.geoJSON(fc as never, {
        interactive: false,
        style: (f) => {
          const hot = hotZones.has(String(f?.properties?.zone_id));
          return {
            color: zoneColor(f?.properties?.zone_type),
            weight: hot ? 10 : 7,
            opacity: hot ? 0.55 : 0.3,
            dashArray: "1 5",
            fill: false,
          };
        },
      }).addTo(layer);
      L.geoJSON(fc as never, {
        style: (f) => {
          const hot = hotZones.has(String(f?.properties?.zone_id));
          const c = zoneColor(f?.properties?.zone_type);
          return {
            color: c,
            weight: hot ? 2.5 : 1.2,
            opacity: hot ? 1 : 0.7,
            fillColor: c,
            fillOpacity: hot ? 0.16 : 0.04,
          };
        },
        onEachFeature: (f, l) => {
          const p = (f.properties ?? {}) as Record<string, unknown>;
          l.bindTooltip(`${esc(p.zone_id)} · ${esc(p.zone_type)}`, { sticky: true });
        },
      }).addTo(layer);
    }

    const liveById = new Map(aircraft.map((a) => [`icao24:${a.properties.icao24}`, a]));
    for (const d of detections) {
      const live = preferLive ? liveById.get(d.entity_id) : undefined;
      const pos: [number, number] | null = live
        ? [live.properties.latitude, live.properties.longitude]
        : typeof d.latitude === "number" && typeof d.longitude === "number"
          ? [d.latitude, d.longitude]
          : null;
      if (!pos) continue;
      const selected = d.detection_id === selectedId;
      const sev = severityColor(d.severity);
      L.circleMarker(pos, {
        radius: live ? 12 : 8,
        color: sev,
        weight: selected ? 4 : 2,
        fillColor: sev,
        fillOpacity: live ? 0.15 : 0.5,
        dashArray: live ? undefined : "3 3",
      })
        .bindPopup(
          `<b>${esc(d.entity_id)}</b><br/>zone: ${esc(d.zone_name ?? d.zone_id)} (${esc(d.zone_type)})` +
            `<br/>severity: ${esc(d.severity)}<br/>inside for: ${esc(d.duration_seconds)} s` +
            `<br/>${live ? "live position" : "last known position"}`,
        )
        .addTo(layer);
    }
    return () => {
      layer.remove();
    };
  }, [map, zones, detections, aircraft, selectedId, preferLive]);

  return null;
}
