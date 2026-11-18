// frontend/src/pages/overlays/TrackLayer.tsx
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import { fetchJSON } from "../../api/client";

export function TrackLayer({ entityId }: { entityId: string | null }) {
  const map = useLeafletMap();

  useEffect(() => {
    if (!map || !entityId) return;
    const controller = new AbortController();
    let line: L.GeoJSON | null = null;
    fetchJSON<any>("/observations/tracks", { entity_id: entityId }, controller.signal)
      .then((geojson) => {
        line = L.geoJSON(geojson, { style: { color: "#facc15", weight: 3 } }).addTo(map);
      })
      .catch(() => {}); // no track is fine
    return () => {
      controller.abort();
      line?.remove();
    };
  }, [map, entityId]);

  return null;
}