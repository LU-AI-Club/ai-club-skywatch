// A ripple where a brand-new incursion happened.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import type { Detection } from "../../../api/types";
import { severityColor } from "../severity";
import { useReplayAt } from "./replayContext";

export function PingLayer({ detections, pingIds }: { detections: Detection[]; pingIds?: ReadonlySet<string> }) {
  const map = useLeafletMap();
  const replaying = useReplayAt() != null;
  useEffect(() => {
    if (!map || replaying || !pingIds || pingIds.size === 0) return;
    const layer = L.layerGroup().addTo(map);
    for (const d of detections) {
      if (!pingIds.has(d.detection_id)) continue;
      if (typeof d.latitude !== "number" || typeof d.longitude !== "number") continue;
      const c = severityColor(d.severity);
      L.marker([d.latitude, d.longitude], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: "nfz-ping",
          html: `<i style="--pc:${c}"></i><i style="--pc:${c}"></i><i style="--pc:${c}"></i>`,
          iconSize: [0, 0],
          iconAnchor: [0, 0],
        }),
      }).addTo(layer);
    }
    return () => {
      layer.remove();
    };
  }, [map, pingIds, detections, replaying]);
  return null;
}
