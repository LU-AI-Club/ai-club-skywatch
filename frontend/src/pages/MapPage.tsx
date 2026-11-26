// The shared map page: live aircraft plus per-detector overlay modes you can
// toggle on and off. Each overlay reads its detector's endpoint and plots a
// point per detection. This page is platform-owned (shared design); the three
// detector dashboards are each team's own.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { MapView } from "../map/MapView";
import { useLeafletMap } from "../map/mapContext";
import { useObservations } from "../api/observations";
import {
  useSpoofingDetections,
  useProximityDetections,
  useNoFlyZoneDetections,
} from "../api/hooks";
import type { Detection } from "../api/types";
import { SpoofingOverlay } from "./overlays/SpoofingOverlay";

// Detector-specific overlays. A key present here replaces the generic dot with
// that team's own component; a key absent falls back to DetectionOverlay, so
// adding one is additive and removing one cannot break the map.
const TEAM_OVERLAYS: Partial<
  Record<OverlayKey, (props: { detections: Detection[] }) => JSX.Element | null>
> = {
  spoofing: SpoofingOverlay,
};
import { ProximityOverlay } from "./overlays/ProximityOverlay";

const OVERLAYS = [
  { key: "spoofing", label: "Spoofing", color: "#a855f7" },
  { key: "proximity", label: "Proximity", color: "#22d3ee" },
  { key: "no-fly-zone", label: "No-fly zone", color: "#f59e0b" },
] as const;

type OverlayKey = (typeof OVERLAYS)[number]["key"];

const SINCE_HOURS = 2;

// A detector overlay: renders markers for detections that carry coordinates,
// and cleans itself up. Rendered inside <MapView>, so it can grab the raw map.
function DetectionOverlay({
  detections,
  color,
}: {
  detections: Detection[];
  color: string;
}) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    for (const d of detections) {
      if (typeof d.latitude === "number" && typeof d.longitude === "number") {
        L.circleMarker([d.latitude, d.longitude], {
          radius: 9,
          color,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.25,
        })
          .bindPopup(
            `<b>${d.detector_id ?? "detection"}</b><br/>severity: ${d.severity}<br/>confidence: ${
              typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—"
            }`,
          )
          .addTo(layer);
      }
    }
    return () => {
      layer.remove();
    };
  }, [map, detections, color]);
  return null;
}

export function MapPage() {
  const [on, setOn] = useState<Record<OverlayKey, boolean>>({
    spoofing: true,
    proximity: true,
    "no-fly-zone": true,
  });
  const { aircraft, lastUpdated, error } = useObservations();

  // All three always fetch (cheap); overlays render only when toggled on.
  // 2 h while the proximity overlay is in development: recent detections still
  // have both aircraft in the live feed. Was 24 h.
  const spoofing = useSpoofingDetections({ since_hours: SINCE_HOURS });
  const proximity = useProximityDetections({ since_hours: SINCE_HOURS });
  const noFlyZone = useNoFlyZoneDetections({ since_hours: SINCE_HOURS });
  const data: Record<OverlayKey, Detection[] | null> = {
    spoofing: spoofing.data,
    proximity: proximity.data,
    "no-fly-zone": noFlyZone.data,
  };

  return (
    <div className="map-page">
      <div className="map-toggles">
        {OVERLAYS.map((o) => (
          <label key={o.key}>
            <input
              type="checkbox"
              checked={on[o.key]}
              onChange={(e) => setOn((s) => ({ ...s, [o.key]: e.target.checked }))}
            />
            <span className="swatch" style={{ background: o.color }} />
            {o.label}
            {data[o.key] ? ` (${data[o.key]!.length})` : ""}
          </label>
        ))}
      </div>

      <MapView style={{ height: "100%" }}>
        {OVERLAYS.map((o) => {
          if (!on[o.key] || !data[o.key]) return null;
          // A team that has built its own overlay renders that instead of the
          // generic dot. Kept as a lookup so each team owns its own file and
          // three teams are not editing one block.
          const Own = TEAM_OVERLAYS[o.key];
          return Own ? (
            <Own key={o.key} detections={data[o.key]!} />
          ) : (
            <DetectionOverlay key={o.key} detections={data[o.key]!} color={o.color} />
          );
          // Proximity finds pairs, so it draws its own overlay (a line between
          // the two aircraft); the others are one-aircraft findings, so a dot.
          const Overlay = o.key === "proximity" ? ProximityOverlay : DetectionOverlay;
          return <Overlay key={o.key} detections={data[o.key]!} color={o.color} />;
        })}
      </MapView>

      <div className="map-status">
        {error
          ? `API unavailable — ${error}`
          : `${aircraft.length} aircraft${
              lastUpdated ? ` · updated ${lastUpdated.toLocaleTimeString()}` : ""
            }`}
      </div>
    </div>
  );
}
