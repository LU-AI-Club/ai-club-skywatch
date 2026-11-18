// Measure distance and bearing on the map: click a start point, then an end
// point. Shows nautical miles and the true bearing, like plotting on a chart.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { nmBetween } from "../geo";
import { bearing } from "../track";

export function measureLabel(a: { lat: number; lon: number }, b: { lat: number; lon: number }): string {
  const nm = nmBetween(a, b);
  const brg = Math.round(bearing(a, b)) % 360;
  return `${nm < 10 ? nm.toFixed(1) : Math.round(nm)} NM · ${String(brg).padStart(3, "0")}°T`;
}

export function MeasureTool({ active, onDone }: { active: boolean; onDone: () => void }) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map || !active) return;
    const el = map.getContainer();
    el.classList.add("nfz-measuring");
    const layer = L.layerGroup().addTo(map);
    let start: L.LatLng | null = null;
    let fixed = false;
    const line = L.polyline([], { color: "#fde047", weight: 2, dashArray: "6 5", interactive: false }).addTo(layer);
    const label = L.marker([0, 0], {
      interactive: false,
      keyboard: false,
      icon: L.divIcon({ className: "nfz-measure-label", html: "<span></span>", iconSize: [0, 0], iconAnchor: [0, 0] }),
    });
    const dot = (ll: L.LatLng) =>
      L.circleMarker(ll, { radius: 4, color: "#fde047", weight: 2, fillColor: "#0a0a0c", fillOpacity: 1, interactive: false }).addTo(layer);

    const draw = (end: L.LatLng) => {
      if (!start) return;
      line.setLatLngs([start, end]);
      const mid = L.latLng((start.lat + end.lat) / 2, (start.lng + end.lng) / 2);
      label.setLatLng(mid);
      if (!layer.hasLayer(label)) label.addTo(layer);
      const span = label.getElement()?.querySelector("span");
      if (span) span.textContent = measureLabel({ lat: start.lat, lon: start.lng }, { lat: end.lat, lon: end.lng });
    };
    const onClick = (e: L.LeafletMouseEvent) => {
      if (!start || fixed) {
        layer.clearLayers();
        line.setLatLngs([]).addTo(layer);
        start = e.latlng;
        fixed = false;
        dot(start);
        return;
      }
      draw(e.latlng);
      dot(e.latlng);
      fixed = true;
    };
    const onMove = (e: L.LeafletMouseEvent) => {
      if (start && !fixed) draw(e.latlng);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onDone();
    map.on("click", onClick);
    map.on("mousemove", onMove);
    window.addEventListener("keydown", onKey);
    return () => {
      el.classList.remove("nfz-measuring");
      map.off("click", onClick);
      map.off("mousemove", onMove);
      window.removeEventListener("keydown", onKey);
      layer.remove();
    };
  }, [map, active, onDone]);
  return null;
}
