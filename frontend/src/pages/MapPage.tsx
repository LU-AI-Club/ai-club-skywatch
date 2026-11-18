// The shared map page: live aircraft plus per-detector overlay modes you can
// toggle on and off. This page is platform-owned (shared design); the three
// detector dashboards are each team's own.
//
// The map itself is the LiveMap component (pages/nfz/components/LiveMap.tsx,
// built by the NFZ team and shared with its dashboard): chart-style basemap,
// plane icons with trails and data tags, HUD, layer switches, aircraft search,
// flight strips, measuring tool, fullscreen. Each detector still plugs in as
// a child overlay, exactly as before: the Spoofing and Proximity overlays
// below are unchanged.
//
// Links: /map?ac=<icao hex> selects and follows an aircraft;
// /map?d=<no-fly-zone detection id> flies to that incursion.
import { useEffect, useMemo, useRef, useState } from "react";
import * as L from "leaflet";
import { useSearchParams } from "react-router-dom";
import { useLeafletMap } from "../map/mapContext";
import {
  useSpoofingDetections,
  useProximityDetections,
  useNoFlyZoneDetections,
} from "../api/hooks";
import type { Detection } from "../api/types";
import { NoFlyZoneOverlay } from "./overlays/NoFlyZoneOverlay";
import { LiveMap, type LiveMapHandle } from "./nfz/components/LiveMap";
import { useFeedHealth } from "./nfz/hooks/useFeedHealth";
import { useFreshIds } from "./nfz/hooks/useFreshIds";
import { useHotkeys } from "./nfz/hooks/useHotkeys";

const OVERLAYS = [
  { key: "spoofing", label: "Spoofing", color: "#a855f7" },
  { key: "proximity", label: "Proximity", color: "#22d3ee" },
  { key: "no-fly-zone", label: "No-fly zone", color: "#e040fb" },
] as const;

type OverlayKey = (typeof OVERLAYS)[number]["key"];

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
  const [params] = useSearchParams();
  const mapRef = useRef<LiveMapHandle>(null);
  const health = useFeedHealth();

  // All three always fetch (cheap); overlays render only when toggled on.
  const spoofing = useSpoofingDetections({ since_hours: 24 });
  const proximity = useProximityDetections({ since_hours: 24 });
  const noFlyZone = useNoFlyZoneDetections({ since_hours: 24 });
  // Detections are events, not moving dots: re-poll so new ones appear.
  const reloadNoFlyZone = noFlyZone.reload;
  useEffect(() => {
    const id = window.setInterval(reloadNoFlyZone, 30_000);
    return () => window.clearInterval(id);
  }, [reloadNoFlyZone]);
  const data: Record<OverlayKey, Detection[] | null> = {
    spoofing: spoofing.data,
    proximity: proximity.data,
    "no-fly-zone": noFlyZone.data,
  };

  // Every detection from the overlays that are on: these flag aircraft
  // (lock-on brackets) and list in each aircraft's flight strip.
  const flagged = useMemo(
    () => OVERLAYS.flatMap((o) => (on[o.key] ? (data[o.key] ?? []) : [])),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [on, spoofing.data, proximity.data, noFlyZone.data],
  );
  const fresh = useFreshIds(noFlyZone.data);

  const nfzId = params.get("d");
  const flyPoint = useMemo(() => {
    const d = noFlyZone.data?.find((x) => x.detection_id === nfzId);
    return d && typeof d.latitude === "number" && typeof d.longitude === "number"
      ? { lat: d.latitude, lon: d.longitude, key: d.detection_id }
      : null;
  }, [noFlyZone.data, nfzId]);

  useHotkeys({
    f: () => mapRef.current?.toggleFullscreen(),
    "/": () => mapRef.current?.focusSearch(),
    Escape: () => mapRef.current?.clearSelection(),
  });

  return (
    <div className="map-page nfz-mappage">
      <LiveMap
        ref={mapRef}
        flagged={flagged}
        flaggedLabel="detections"
        selectedDetectionId={nfzId}
        health={health}
        zonesInLegend={on["no-fly-zone"]}
        flyPoint={flyPoint}
        initialAircraft={params.get("ac")}
      >
        {OVERLAYS.map((o) =>
          o.key !== "no-fly-zone" && on[o.key] && data[o.key] ? (
            <DetectionOverlay key={o.key} detections={data[o.key]!} color={o.color} />
          ) : null,
        )}
        {on["no-fly-zone"] && (
          <NoFlyZoneOverlay
            detections={noFlyZone.data ?? []}
            selectedId={nfzId}
            traffic="none"
            pingIds={fresh}
            dashboardLinks
          />
        )}
      </LiveMap>

      <div className="nfz-deck" role="group" aria-label="Detector overlays">
        <div className="nfz-deck-title">Detectors · 24 h</div>
        {OVERLAYS.map((o) => {
          const rows = data[o.key];
          const err = o.key === "spoofing" ? spoofing.error : o.key === "proximity" ? proximity.error : noFlyZone.error;
          return (
            <label key={o.key} className={on[o.key] ? "is-on" : undefined} style={{ ["--dc" as string]: o.color }}>
              <input
                type="checkbox"
                checked={on[o.key]}
                onChange={(e) => setOn((s) => ({ ...s, [o.key]: e.target.checked }))}
              />
              <span className="nfz-deck-swatch" />
              <span className="nfz-deck-name">{o.label}</span>
              <span className="nfz-deck-count" title={err ?? undefined}>
                {err ? "!" : rows ? rows.length : "…"}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}
