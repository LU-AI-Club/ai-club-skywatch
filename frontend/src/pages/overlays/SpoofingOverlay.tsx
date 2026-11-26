// Deliverable 3 — the spoofing overlay on the shared map.
//
// The generic overlay drops one dot per detection, which tells you a finding
// happened somewhere. For spoofing that is the least interesting half: our
// findings are about an aircraft's *path* disagreeing with what it claimed, and
// a single dot cannot show a disagreement.
//
// So this draws the aircraft's recent track as well, and puts the marker on the
// anomaly. Tracks are fetched per aircraft and only for the handful of flagged
// ones, never for the whole sky.
import { useEffect, useRef, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import { fetchJSON } from "../../api/client";
import type { Detection } from "../../api/types";

const COLOR = "#a855f7";

// Severity decides how loud a marker is. Everything is visible; HIGH is just
// unmissable, because the point of a map is finding the one that matters.
const RADIUS: Record<string, number> = {
  critical: 13,
  high: 11,
  medium: 9,
  low: 7,
};

interface TrackPoint {
  observed_at: string;
  latitude: number;
  longitude: number;
}

interface TrackResponse {
  geometry?: { coordinates?: [number, number][] };
  properties?: { points?: TrackPoint[] };
}

function severityKey(d: Detection): string {
  return String(d.severity ?? "").toLowerCase();
}

function gateOf(d: Detection): string {
  const m = d.metadata;
  if (m && typeof m === "object") {
    const g = (m as Record<string, unknown>).gate;
    if (typeof g === "string") return g;
  }
  return d.detection_type ?? "detection";
}

function popupHtml(d: Detection): string {
  const gate = gateOf(d);
  const conf = typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—";
  const m = (d.metadata ?? {}) as Record<string, unknown>;
  const facts = Array.isArray(m.explanation_facts)
    ? (m.explanation_facts as unknown[]).filter((f): f is string => typeof f === "string")
    : [];
  // The detector's own sentence, not a re-description of the row.
  const why = facts.length ? `<br/><span style="opacity:.85">${facts[0]}</span>` : "";
  return (
    `<b>${gate}</b><br/>` +
    `${d.entity_id}<br/>` +
    `severity: ${d.severity} &middot; confidence: ${conf}${why}`
  );
}

export function SpoofingOverlay({ detections }: { detections: Detection[] }) {
  const map = useLeafletMap();
  const [tracks, setTracks] = useState<Record<string, [number, number][]>>({});
  const wanted = useRef<Set<string>>(new Set());

  // Fetch each flagged aircraft's path once. Keyed by entity_id, so an
  // aircraft flagged by two rules is fetched once, not twice.
  useEffect(() => {
    const ids = Array.from(new Set(detections.map((d) => d.entity_id).filter(Boolean)));
    const missing = ids.filter((id) => !wanted.current.has(id));
    if (missing.length === 0) return;
    missing.forEach((id) => wanted.current.add(id));

    let cancelled = false;
    (async () => {
      for (const id of missing) {
        try {
          const r = await fetchJSON<TrackResponse>("/observations/tracks", {
            entity_id: id,
            lookback_hours: 2,
          });
          const coords = r?.geometry?.coordinates ?? [];
          // GeoJSON is [lon, lat]; Leaflet wants [lat, lon]. Getting this
          // backwards puts Virginia aircraft in the Indian Ocean.
          const latlngs = coords.map(([lon, lat]) => [lat, lon] as [number, number]);
          if (!cancelled && latlngs.length > 1) {
            setTracks((prev) => ({ ...prev, [id]: latlngs }));
          }
        } catch {
          // A missing track is not an error worth showing: the aircraft may
          // have aged out of the observations window. The marker still draws.
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [detections]);

  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);

    for (const d of detections) {
      const sev = severityKey(d);
      const id = d.entity_id;

      // The path this aircraft actually flew, behind the marker.
      const path = tracks[id];
      if (path && path.length > 1) {
        L.polyline(path, {
          color: COLOR,
          weight: 2,
          opacity: 0.5,
          dashArray: "4 6",
        }).addTo(layer);

        // Where the track ends: the aircraft's latest known position. Hollow,
        // so it reads as "here now" rather than as a second finding.
        const last = path[path.length - 1];
        L.circleMarker(last, {
          radius: 4,
          color: COLOR,
          weight: 2,
          fillOpacity: 0,
        })
          .bindTooltip(`${id} — latest position`, { direction: "top" })
          .addTo(layer);
      }

      // The finding itself. Identity rules carry no coordinates by design, so
      // this is skipped for them rather than invented at (0,0).
      if (typeof d.latitude === "number" && typeof d.longitude === "number") {
        L.circleMarker([d.latitude, d.longitude], {
          radius: RADIUS[sev] ?? 8,
          color: COLOR,
          weight: sev === "high" || sev === "critical" ? 3 : 2,
          fillColor: COLOR,
          fillOpacity: sev === "high" || sev === "critical" ? 0.45 : 0.2,
        })
          .bindPopup(popupHtml(d))
          .addTo(layer);
      }
    }

    return () => {
      layer.remove();
    };
  }, [map, detections, tracks]);

  return null;
}
