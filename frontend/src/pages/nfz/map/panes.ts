import type { Map as LeafletMap } from "leaflet";

// Our own Leaflet panes, so layers stack in a sensible order:
//   tiles 200 < chart grid 250 < trails 390 < zones/markers 400 (Leaflet's
//   overlayPane) < chart labels 450 < markers 600 < popups 700.
export const PANES = {
  chart: { name: "nfz-chart", z: 250 },
  trails: { name: "nfz-trails", z: 390 },
  labels: { name: "nfz-labels", z: 450 },
} as const;

export function ensurePane(map: LeafletMap, pane: { name: string; z: number }): string {
  if (!map.getPane(pane.name)) {
    const el = map.createPane(pane.name);
    el.style.zIndex = String(pane.z);
    el.style.pointerEvents = "none";
  }
  return pane.name;
}
