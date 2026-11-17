// Proximity's map overlay. Every other detector finds something about ONE
// aircraft, so a dot is enough. Proximity finds a PAIR, so we draw the pair:
// a line between the two aircraft at the moment the detector evaluated them,
// with a label at the midpoint giving the predicted miss distance and time.
//
// A detection row only stores the midpoint (latitude/longitude). The two
// positions come from each aircraft's track (GET /observations/tracks), taking
// the fix closest in time to that evaluation moment. If either track has no
// fix close enough (e.g. the planes have aged out of the feed), we fall back to
// the plain midpoint dot, so the detection is never silently dropped.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../map/mapContext";
import { fetchJSON } from "../../api/client";
import type { Detection, FeatureCollection } from "../../api/types";

interface TrackPoint {
  observed_at: string;
  latitude: number;
  longitude: number;
  altitude: string | null;
}

interface TrackFeature {
  type: "Feature";
  properties: { entity_id: string; points: TrackPoint[] };
}

interface Evidence {
  evidence_type?: string;
  timestamp?: string;
}

// A fix further than this from the evaluation moment is not "where the plane
// was" any more: at 450 kt, 60 s is 7.5 nm. The poller samples every 10 s, so a
// live pair always has a fix well inside this.
const MAX_FIX_GAP_S = 60;
const MAX_LOOKBACK_HOURS = 168; // the API's cap on /observations/tracks

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// The moment the pair was evaluated: the predicted_closest_approach evidence
// timestamp. t_cpa_seconds is measured from here, and the row's midpoint is the
// two positions at this moment. temporal_bounds_start is the alert's cooldown
// period, which can start up to a period earlier, so it is only a fallback.
function evaluatedAt(d: Detection): Date {
  const evidence = Array.isArray(d.evidence) ? (d.evidence as Evidence[]) : [];
  const cpa = evidence.find((e) => e.evidence_type === "predicted_closest_approach");
  return new Date(cpa?.timestamp ?? d.temporal_bounds_start);
}

function members(d: Detection): [string, string] | null {
  const ids = d.member_entity_ids;
  return Array.isArray(ids) && ids.length === 2 ? [String(ids[0]), String(ids[1])] : null;
}

function closestFix(points: TrackPoint[], at: Date): TrackPoint | null {
  let best: TrackPoint | null = null;
  let bestGap = Infinity;
  for (const p of points) {
    const gap = Math.abs(new Date(p.observed_at).getTime() - at.getTime());
    if (gap < bestGap) {
      best = p;
      bestGap = gap;
    }
  }
  return best && bestGap <= MAX_FIX_GAP_S * 1000 ? best : null;
}

function num(v: unknown, digits: number): string {
  return typeof v === "number" && Number.isFinite(v) ? v.toFixed(digits) : "—";
}

function popupHtml(d: Detection, at: Date, alertCount = 1): string {
  const [a, b] = members(d) ?? [d.entity_id, "?"];
  const repeats =
    alertCount > 1 ? `<br/><i>latest of ${alertCount} alerts for this pair</i>` : "";
  return `
    <b>Proximity · ${escapeHtml(d.severity)}</b><br/>
    ${escapeHtml(a)} ↔ ${escapeHtml(b)}<br/>
    Predicted miss: ${num(d.predicted_horizontal_nm, 2)} nm, ${num(d.predicted_vertical_ft, 0)} ft<br/>
    Closest approach in: ${num(d.t_cpa_seconds, 0)} s<br/>
    Evaluated at: ${escapeHtml(at.toLocaleTimeString())}<br/>
    Confidence: ${num(d.confidence, 2)}${repeats}`;
}

// An ongoing encounter is alerted once per cooldown period, so one pair can
// have several rows (decided with the Tech Lead: the front end groups them).
// Draw one line per pair -- the most recent alert -- and remember the count.
function latestPerPair(detections: Detection[]): { detection: Detection; count: number }[] {
  const groups = new Map<string, { detection: Detection; count: number }>();
  for (const d of detections) {
    const pair = members(d);
    const key = pair ? [...pair].sort().join("|") : d.detection_id;
    const seen = groups.get(key);
    if (!seen) {
      groups.set(key, { detection: d, count: 1 });
    } else {
      seen.count += 1;
      if (evaluatedAt(d) > evaluatedAt(seen.detection)) seen.detection = d;
    }
  }
  return [...groups.values()];
}

export function ProximityOverlay({
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
    const controller = new AbortController();

    // One track request per aircraft, even if it appears in several detections.
    // Look back far enough to reach the oldest detection on screen.
    const oldest = Math.min(...detections.map((d) => evaluatedAt(d).getTime()), Date.now());
    const lookbackHours = Math.min(MAX_LOOKBACK_HOURS, (Date.now() - oldest) / 3_600_000 + 0.5);
    const tracks = new Map<string, Promise<TrackPoint[]>>();
    const trackOf = (entityId: string) => {
      if (!tracks.has(entityId)) {
        tracks.set(
          entityId,
          fetchJSON<FeatureCollection<TrackFeature>>(
            "/observations/tracks",
            { entity_id: entityId, lookback_hours: lookbackHours },
            controller.signal,
          ).then((fc) => fc.features[0]?.properties.points ?? []),
        );
      }
      return tracks.get(entityId)!;
    };

    const drawMidpointDot = (d: Detection, count: number) => {
      if (typeof d.latitude !== "number" || typeof d.longitude !== "number") return;
      L.circleMarker([d.latitude, d.longitude], {
        radius: 9,
        color,
        weight: 2,
        fillColor: color,
        fillOpacity: 0.25,
      })
        .bindPopup(popupHtml(d, evaluatedAt(d), count) + "<br/><i>aircraft positions unavailable</i>")
        .addTo(layer);
    };

    for (const { detection: d, count } of latestPerPair(detections)) {
      const pair = members(d);
      if (!pair) {
        drawMidpointDot(d, count);
        continue;
      }
      const at = evaluatedAt(d);
      Promise.all(pair.map(trackOf))
        .then(([trackA, trackB]) => {
          if (controller.signal.aborted) return;
          const a = closestFix(trackA, at);
          const b = closestFix(trackB, at);
          if (!a || !b) {
            drawMidpointDot(d, count);
            return;
          }
          const pa: L.LatLngTuple = [a.latitude, a.longitude];
          const pb: L.LatLngTuple = [b.latitude, b.longitude];
          const mid: L.LatLngTuple = [(pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2];
          const popup = popupHtml(d, at, count);

          L.polyline([pa, pb], { color, weight: 3, opacity: 0.9 }).bindPopup(popup).addTo(layer);
          for (const [p, id] of [
            [pa, pair[0]],
            [pb, pair[1]],
          ] as const) {
            L.circleMarker(p, { radius: 5, color, weight: 2, fillColor: "#0a0a0c", fillOpacity: 1 })
              .bindTooltip(escapeHtml(id))
              .addTo(layer);
          }
          L.circleMarker(mid, { radius: 4, color, weight: 2, fillColor: color, fillOpacity: 1 })
            .bindTooltip(`${num(d.predicted_horizontal_nm, 2)} nm · ${num(d.t_cpa_seconds, 0)} s`, {
              permanent: true,
              direction: "top",
              className: "proximity-label",
            })
            .bindPopup(popup)
            .addTo(layer);
        })
        .catch((err: Error) => {
          if (err.name !== "AbortError") drawMidpointDot(d, count);
        });
    }

    return () => {
      controller.abort();
      layer.remove();
    };
  }, [map, detections, color]);

  return null;
}
