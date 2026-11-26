// Map overlays for the no-fly-zone page, rendered inside <MapView>: zone
// polygons (colored by type, highlighted when they have incursions or are
// selected) and one marker per incursion. Clicking either selects it.
import { useEffect, useRef } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import type { Detection } from "../../api/types";
import {
  escapeHtml,
  fmtAltBand,
  isOngoing,
  zoneColor,
  zoneNameOf,
  type ZoneFeature,
} from "./zones";

export function ZoneLayer({
  zones,
  hitCounts,
  selectedZone,
  onSelectZone,
}: {
  zones: ZoneFeature[];
  hitCounts: Map<string, number>;
  selectedZone: string | null;
  onSelectZone: (zoneId: string | null) => void;
}) {
  const map = useLeafletMap();
  const selectRef = useRef(onSelectZone);
  selectRef.current = onSelectZone;

  useEffect(() => {
    if (!map || !zones.length) return;
    const layer = L.geoJSON(zones as unknown as GeoJSON.FeatureCollection["features"], {
      style: (f) => {
        const p = (f as unknown as ZoneFeature).properties;
        const color = zoneColor(p.zone_type);
        const selected = p.zone_id === selectedZone;
        const hot = (hitCounts.get(p.zone_id) ?? 0) > 0;
        return {
          color,
          weight: selected ? 3 : hot ? 2 : 1,
          opacity: selected || hot ? 1 : 0.7,
          fillColor: color,
          fillOpacity: selected ? 0.3 : hot ? 0.18 : 0.06,
          dashArray: p.activation === "ALWAYS" ? undefined : "5 4",
        };
      },
      onEachFeature: (f, lyr) => {
        const p = (f as unknown as ZoneFeature).properties;
        const n = hitCounts.get(p.zone_id) ?? 0;
        lyr.bindTooltip(
          `<b>${escapeHtml(p.zone_id)}</b> · ${escapeHtml(p.zone_type)}<br/>` +
            `${escapeHtml(fmtAltBand(p))}<br/>` +
            `${n} incursion${n === 1 ? "" : "s"} in window`,
          { sticky: true },
        );
        lyr.on("click", () => selectRef.current(p.zone_id));
      },
    }).addTo(map);
    layer.bringToBack();
    return () => {
      layer.remove();
    };
  }, [map, zones, hitCounts, selectedZone]);

  return null;
}

export function IncursionLayer({
  detections,
  selectedId,
  onSelect,
}: {
  detections: Detection[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const map = useLeafletMap();
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;

  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    for (const d of detections) {
      if (typeof d.latitude !== "number" || typeof d.longitude !== "number") continue;
      const selected = d.detection_id === selectedId;
      const color = zoneColor(String(d.zone_type));
      const marker = L.circleMarker([d.latitude, d.longitude], {
        radius: selected ? 10 : 7,
        color: selected ? "#ffffff" : "#0a0a0c",
        weight: selected ? 3 : 1.5,
        fillColor: color,
        fillOpacity: 0.95,
        className: isOngoing(d) ? "nfz-pulse" : undefined,
      })
        .bindTooltip(
          `<b>${escapeHtml(d.entity_id)}</b> in ${escapeHtml(zoneNameOf(d))}<br/>` +
            `${escapeHtml(d.severity)} · ${isOngoing(d) ? "ongoing" : "ended"}`,
        )
        .on("click", () => selectRef.current(d.detection_id))
        .addTo(layer);
      if (selected) marker.bringToFront();
    }
    return () => {
      layer.remove();
    };
  }, [map, detections, selectedId]);

  return null;
}

// Pans/zooms the map to whatever was last selected.
export function FlyTo({ target }: { target: L.LatLngExpression | L.LatLngBounds | null }) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map || !target) return;
    if (target instanceof L.LatLngBounds) {
      map.flyToBounds(target, { padding: [30, 30], maxZoom: 11, duration: 0.6 });
    } else {
      map.flyTo(target, Math.max(map.getZoom(), 11), { duration: 0.6 });
    }
  }, [map, target]);
  return null;
}
