// Helpers a case-map overlay uses to draw without boilerplate. A team's overlay
// calls these instead of wiring up Leaflet layers and track fetches by hand.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import { fetchJSON } from "../../api/client";

// A LayerGroup that lives on the map for as long as your overlay is mounted and
// is removed (with everything you added to it) when the case changes or the
// overlay unmounts. Draw everything into this group so cleanup is automatic.
// Returns null until the map is ready.
export function useCaseLayer(): L.LayerGroup | null {
  const map = useLeafletMap();
  const [layer, setLayer] = useState<L.LayerGroup | null>(null);
  useEffect(() => {
    if (!map) return;
    const group = L.layerGroup().addTo(map);
    setLayer(group);
    return () => {
      group.remove();
      setLayer(null);
    };
  }, [map]);
  return layer;
}

export interface TrackPoint {
  observed_at: string;
  latitude: number;
  longitude: number;
  sog: number | null;
  cog: number | null;
  heading: number | null;
  altitude: string | null;
}

export interface AircraftTrack {
  // Leaflet order ([lat, lon]) so it drops straight into L.polyline.
  latlngs: [number, number][];
  points: TrackPoint[];
  latest: [number, number] | null;
}

// Fetch one aircraft's recent track from the API as [lat, lon] pairs ready for
// Leaflet. Accepts either an `aircraft:<hex>` / `icao24:<hex>` id or a bare hex:
// detections carry `aircraft:<hex>` but observations are keyed `icao24:<hex>`,
// so we always send the bare hex and let the API normalize it.
export function useAircraftTrack(
  entityId: string | null | undefined,
  lookbackHours = 24,
): AircraftTrack | null {
  const [track, setTrack] = useState<AircraftTrack | null>(null);
  useEffect(() => {
    if (!entityId) {
      setTrack(null);
      return;
    }
    const hex = entityId.includes(":") ? entityId.split(":").pop()! : entityId;
    let cancelled = false;
    fetchJSON<{ features: Array<{ geometry: { coordinates: [number, number][] }; properties: { points: TrackPoint[] } }> }>(
      "/observations/tracks",
      { entity_id: hex, lookback_hours: lookbackHours },
    )
      .then((fc) => {
        if (cancelled) return;
        const feature = fc.features?.[0];
        const coords = feature?.geometry?.coordinates ?? [];
        const latlngs = coords.map(([lon, lat]) => [lat, lon] as [number, number]);
        setTrack({
          latlngs,
          points: feature?.properties?.points ?? [],
          latest: latlngs.length ? latlngs[latlngs.length - 1] : null,
        });
      })
      .catch(() => {
        if (!cancelled) setTrack(null);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, lookbackHours]);
  return track;
}
