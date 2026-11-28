// The shared starter overlay. Until a team customizes their own case overlay,
// every detector's case map uses this: it draws the involved aircraft's recent
// track, a dot at its latest position, and a ring at the detection's location,
// then frames them. It is intentionally generic — a team replaces it with a
// picture of THEIR finding (see caseMap/overlays/<Detector>CaseOverlay.tsx).
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import type { CaseOverlayProps } from "../caseTypes";
import { useCaseLayer, useAircraftTrack } from "./hooks";

const TRACK_COLOR = "#22d3ee"; // the aircraft's path
const DETECTION_COLOR = "#f97316"; // where the detector fired

export function DefaultCaseOverlay({ row }: CaseOverlayProps) {
  const map = useLeafletMap();
  const layer = useCaseLayer();
  const track = useAircraftTrack(row.entity_id);

  useEffect(() => {
    if (!map || !layer) return;
    layer.clearLayers();
    const frame: L.LatLngExpression[] = [];

    // The aircraft's recent path and where it is now.
    if (track && track.latlngs.length) {
      L.polyline(track.latlngs, {
        color: TRACK_COLOR,
        weight: 2,
        opacity: 0.85,
      }).addTo(layer);
      if (track.latest) {
        L.circleMarker(track.latest, {
          radius: 5,
          color: TRACK_COLOR,
          fillColor: TRACK_COLOR,
          fillOpacity: 0.9,
          weight: 1,
        })
          .bindTooltip(row.entity_id, { direction: "top" })
          .addTo(layer);
      }
      frame.push(...track.latlngs);
    }

    // Where the detector says it happened.
    if (row.latitude != null && row.longitude != null) {
      L.circleMarker([row.latitude, row.longitude], {
        radius: 11,
        color: DETECTION_COLOR,
        weight: 2,
        fill: false,
      })
        .bindTooltip(`${row.detection_type || "detection"}`, { direction: "top" })
        .addTo(layer);
      frame.push([row.latitude, row.longitude]);
    }

    // Frame whatever we drew.
    if (frame.length === 1) {
      map.setView(frame[0], 12);
    } else if (frame.length > 1) {
      map.fitBounds(L.latLngBounds(frame).pad(0.3), { maxZoom: 13 });
    }
  }, [map, layer, track, row]);

  return null;
}
