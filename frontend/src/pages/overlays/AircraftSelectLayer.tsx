// frontend/src/pages/overlays/AircraftSelectLayer.tsx
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import { useObservations } from "../../api/observations";

export const entityIdOf = (icao24: string) => `icao24:${icao24}`;

export function AircraftSelectLayer({
  selectedId,
  onSelect,
}: {
  selectedId: string | null;
  onSelect: (entityId: string) => void;
}) {
  const map = useLeafletMap();
  const { aircraft } = useObservations();

  useEffect(() => {
    if (!map) return;
    // Own pane so our markers always sit above MapView's aircraft dots
    const paneName = "aircraftSelect";
    const pane = map.getPane(paneName) ?? map.createPane(paneName);
    pane.style.zIndex = "450";

    const layer = L.layerGroup().addTo(map);
    for (const f of aircraft) {
      const [lon, lat] = f.geometry.coordinates;
      const id = entityIdOf(f.properties.icao24);
      const selected = id === selectedId;
      L.circleMarker([lat, lon], {
        pane: paneName,
        radius: selected ? 11 : 8,
        color: "#3d4952",
        weight: 2,
        opacity: selected ? 1 : 0,
        fill: true,
        fillColor: "#3d4952",
        fillOpacity: 0,
      })
        .on("click", () => onSelect(id))
        .addTo(layer);
    }
    return () => {
      layer.remove();
    };
  }, [map, aircraft, selectedId, onSelect]);

  return null;
}