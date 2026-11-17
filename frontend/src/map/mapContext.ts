import { createContext, useContext } from "react";
import type { Map as LeafletMap } from "leaflet";

// The raw Leaflet map instance, shared with anything rendered inside <MapView>.
// Teams grab it with useLeafletMap() and do whatever they want — add layers,
// controls, handlers. It is null until the map has mounted.
export const MapContext = createContext<LeafletMap | null>(null);

export function useLeafletMap(): LeafletMap | null {
  return useContext(MapContext);
}
