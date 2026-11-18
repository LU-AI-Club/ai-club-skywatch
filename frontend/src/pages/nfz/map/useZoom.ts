import { useEffect, useState } from "react";
import type { Map as LeafletMap } from "leaflet";

/** The map's zoom level, updated after each zoom. */
export function useZoom(map: LeafletMap | null): number | null {
  const [zoom, setZoom] = useState<number | null>(null);
  useEffect(() => {
    if (!map) return;
    const onZoom = () => setZoom(map.getZoom());
    onZoom();
    map.on("zoomend", onZoom);
    return () => {
      map.off("zoomend", onZoom);
    };
  }, [map]);
  return zoom;
}
