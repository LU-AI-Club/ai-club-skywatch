// Where each incursion was detected: a diamond in the severity color. On the
// shared /map (which draws plain aircraft dots) it also rings the aircraft's
// live position for recent incursions.
import { useEffect, useMemo } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { useObservations } from "../../../api/observations";
import type { Detection } from "../../../api/types";
import { severityColor } from "../severity";
import { duration, zuluTime } from "../format";
import { esc } from "./html";
import { asOf, useReplayAt } from "./replayContext";

import { isRecent } from "../flagged";
export { isRecent };

/** Inside the zone at time t: started, and not yet ended. */
function isOpenAt(d: Detection, t: number): boolean {
  const start = Date.parse(String(d.temporal_bounds_start));
  const end = d.temporal_bounds_end ? Date.parse(String(d.temporal_bounds_end)) : Infinity;
  return start <= t && t <= end;
}

export function incursionPopup(d: Detection, dashboardLink = false): string {
  return (
    `<div class="nfz-pop-title"><span class="nfz-pop-sev" style="--sc:${severityColor(d.severity)}">${esc(d.severity)}</span>${esc(d.entity_id)}</div>` +
    `<div>${esc(d.zone_name ?? d.zone_id)} · ${esc(d.zone_type)}</div>` +
    `<div>entered ${esc(zuluTime(d.temporal_bounds_start))}</div>` +
    `<div>inside ${esc(duration(d.duration_seconds))}${d.temporal_bounds_end ? "" : " · still open"}</div>` +
    (dashboardLink
      ? `<a class="nfz-pop-link" href="/no-fly-zone?d=${encodeURIComponent(d.detection_id)}">Open replay in the NFZ dashboard →</a>`
      : "")
  );
}

export function IncursionLayer({
  detections,
  selectedId,
  ringLive,
  onSelect,
  dashboardLinks = false,
}: {
  detections: Detection[];
  selectedId?: string | null;
  /** Ring the live aircraft (only where the map draws its own aircraft dots). */
  ringLive: boolean;
  onSelect?: (d: Detection) => void;
  /** Popups link to the incursion's replay on the NFZ dashboard. */
  dashboardLinks?: boolean;
}) {
  const map = useLeafletMap();
  const { aircraft } = useObservations();
  const at = useReplayAt();
  const shownDetections = useMemo(() => asOf(detections, at), [detections, at]);

  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    const now = at ?? Date.now();
    const replaying = at != null;
    const liveById = ringLive && !replaying ? new Map(aircraft.map((a) => [`icao24:${a.properties.icao24}`, a])) : null;
    for (const d of shownDetections) {
      const color = severityColor(d.severity);
      const selected = d.detection_id === selectedId;
      if (typeof d.latitude === "number" && typeof d.longitude === "number") {
        const m = L.marker([d.latitude, d.longitude], {
          keyboard: false,
          zIndexOffset: selected ? 1000 : 0,
          icon: L.divIcon({
            className: "nfz-hit-icon",
            html: `<span class="nfz-hit${selected ? " is-selected" : ""}${isOpenAt(d, now) ? " is-open" : ""}" style="--sc:${color}"></span>`,
            iconSize: [0, 0],
            iconAnchor: [0, 0],
          }),
        });
        if (onSelect) {
          m.bindTooltip(incursionPopup(d), { className: "nfz-tip", direction: "top", offset: [0, -10] });
          m.on("click", () => onSelect(d));
        } else {
          m.bindPopup(incursionPopup(d, dashboardLinks), { className: "nfz-popup" });
        }
        m.addTo(layer);
      }
      const live = liveById?.get(d.entity_id);
      if (live && (isRecent(d, now) || selected)) {
        L.circleMarker([live.properties.latitude, live.properties.longitude], {
          radius: 13,
          color,
          weight: selected ? 4 : 2,
          fill: false,
          interactive: false,
        }).addTo(layer);
      }
    }
    return () => {
      layer.remove();
    };
  }, [map, shownDetections, at, aircraft, selectedId, ringLive, onSelect, dashboardLinks]);

  return null;
}
