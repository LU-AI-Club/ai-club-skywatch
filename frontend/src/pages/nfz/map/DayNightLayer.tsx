// Night shading with a soft edge along the day/night line. Updates every
// minute.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { ensurePane } from "./panes";
import { nightPolygon } from "./sun";

const PANE = { name: "nfz-night", z: 245 };

export function DayNightLayer() {
  const map = useLeafletMap();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    if (!map) return;
    const pane = ensurePane(map, PANE);
    const ring = nightPolygon(now);
    const line = ring.slice(0, -2);
    const layer = L.layerGroup().addTo(map);
    // Soft edge: two wide, faint strokes along the line, then the fill.
    L.polyline(line, { pane, color: "#020617", weight: 46, opacity: 0.08, interactive: false }).addTo(layer);
    L.polyline(line, { pane, color: "#020617", weight: 18, opacity: 0.1, interactive: false }).addTo(layer);
    L.polygon(ring, { pane, stroke: false, fillColor: "#020617", fillOpacity: 0.3, interactive: false }).addTo(layer);
    return () => {
      layer.remove();
    };
  }, [map, now]);
  return null;
}
