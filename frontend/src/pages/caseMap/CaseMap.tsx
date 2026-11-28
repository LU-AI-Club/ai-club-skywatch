// The focused map shown inside one detection's case. It reuses the shared
// <MapView> (same tiles, same Leaflet instance teams already know) with the live
// aircraft layer turned OFF, centers on the detection, and renders that
// detector's overlay — the team-owned picture of the finding — on top.
import { useEffect } from "react";
import { MapView } from "../../map/MapView";
import { useLeafletMap } from "../../map/mapContext";
import type { CaseRow } from "../caseTypes";
import { CASE_OVERLAYS } from "./registry";
import { DefaultCaseOverlay } from "./DefaultCaseOverlay";

// Centers on the detection and fixes the map's size. The map is created inside a
// panel that lays out after mount, so Leaflet needs invalidateSize() once the
// container has its real dimensions, or tiles render as a grey sliver.
function CaseFocus({ row }: { row: CaseRow }) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const id = window.setTimeout(() => {
      map.invalidateSize();
      if (row.latitude != null && row.longitude != null) {
        map.setView([row.latitude, row.longitude], 11);
      }
    }, 0);
    return () => window.clearTimeout(id);
  }, [map, row]);
  return null;
}

export function CaseMap({ row }: { row: CaseRow }) {
  const Overlay = CASE_OVERLAYS[row._detector] ?? DefaultCaseOverlay;
  return (
    <div className="cases-map">
      <MapView showAircraft={false} showLegend={false}>
        <CaseFocus row={row} />
        <Overlay row={row} />
      </MapView>
    </div>
  );
}
