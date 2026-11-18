// Small map helpers for maps embedded in a scrolling page.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import type { ZoneInfo } from "../zones";

/** The mouse wheel scrolls the page, not the map, until you click the map. */
export function ScrollGuard() {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    map.scrollWheelZoom.disable();
    const on = () => map.scrollWheelZoom.enable();
    const off = () => map.scrollWheelZoom.disable();
    map.on("click", on);
    map.on("mouseout", off);
    return () => {
      map.off("click", on);
      map.off("mouseout", off);
    };
  }, [map]);
  return null;
}

/** Fly to a zone, or to a point, when it changes. */
export function FlyTo({ zone, point }: { zone?: ZoneInfo | null; point?: { lat: number; lon: number; key: string } | null }) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map || !zone) return;
    const bounds = L.geoJSON(zone.feature as never).getBounds();
    if (bounds.isValid()) map.flyToBounds(bounds, { padding: [50, 50], maxZoom: 11, duration: 0.8 });
  }, [map, zone]);
  const key = point?.key;
  useEffect(() => {
    if (!map || !point) return;
    map.flyTo([point.lat, point.lon], Math.max(map.getZoom(), 11), { duration: 0.8 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map, key]);
  return null;
}

/** Tell Leaflet its box changed size (after fullscreen, layout changes). */
export function InvalidateOnChange({ dep }: { dep: unknown }) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const id = window.setTimeout(() => map.invalidateSize(), 60);
    return () => window.clearTimeout(id);
  }, [map, dep]);
  return null;
}
