// The detail panel's mini map: the aircraft's recorded track, the part already
// "flown" in the replay drawn bright, where it entered and left the zone, and
// a plane icon at the replay's current moment.
import { useEffect, useRef } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { altitudeColor } from "../altitude";
import { sampleTrack, type TrackPoint } from "../track";
import { PLANE_PATH } from "./TrafficLayer";

export function ReplayLayer({
  points,
  t,
  entry,
  exit,
  fallback,
}: {
  points: TrackPoint[];
  t: number;
  entry: number | null; // ms: when it entered the zone
  exit: number | null; // ms: when it left (null = still inside)
  fallback: { lat: number; lon: number } | null; // detection point, if no track
}) {
  const map = useLeafletMap();
  const flown = useRef<L.Polyline | null>(null);
  const plane = useRef<L.Marker | null>(null);

  // The whole track, entry/exit marks, and the initial view.
  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    if (points.length >= 2) {
      const ll = points.map((p) => [p.lat, p.lon] as [number, number]);
      L.polyline(ll, { color: "#f4f4f6", weight: 1.5, opacity: 0.35, dashArray: "4 5", interactive: false }).addTo(layer);
      flown.current = L.polyline([], { color: "#22d3ee", weight: 3, opacity: 0.95, interactive: false }).addTo(layer);
      const mark = (time: number | null, cls: string, label: string) => {
        if (time == null) return;
        const s = sampleTrack(points, time);
        if (!s) return;
        L.marker([s.lat, s.lon], {
          interactive: false,
          keyboard: false,
          icon: L.divIcon({ className: `nfz-gate ${cls}`, html: `<i></i><span>${label}</span>`, iconSize: [0, 0], iconAnchor: [0, 0] }),
        }).addTo(layer);
      };
      mark(entry, "is-in", "IN");
      mark(exit, "is-out", "OUT");
      plane.current = L.marker(ll[0], {
        interactive: false,
        keyboard: false,
        zIndexOffset: 1000,
        icon: L.divIcon({
          className: "nfz-ac nfz-replay-plane",
          html: `<div class="nfz-ac-inner" style="--ac:#f4f4f6"><svg viewBox="0 0 24 24"><path d="${PLANE_PATH}"/></svg></div>`,
          iconSize: [0, 0],
          iconAnchor: [0, 0],
        }),
      }).addTo(layer);
      map.fitBounds(L.latLngBounds(ll), { padding: [24, 24], maxZoom: 12 });
    } else if (fallback) {
      map.setView([fallback.lat, fallback.lon], 11);
    }
    return () => {
      layer.remove();
      flown.current = null;
      plane.current = null;
    };
  }, [map, points, entry, exit, fallback?.lat, fallback?.lon]); // eslint-disable-line react-hooks/exhaustive-deps

  // Move the plane and grow the flown line as the replay clock runs.
  useEffect(() => {
    if (!points.length || !plane.current || !flown.current) return;
    const s = sampleTrack(points, t);
    if (!s) return;
    const done = points.slice(0, s.index + 1).map((p) => [p.lat, p.lon] as [number, number]);
    done.push([s.lat, s.lon]);
    flown.current.setLatLngs(done);
    flown.current.setStyle({ color: altitudeColor(s.alt) });
    plane.current.setLatLng([s.lat, s.lon]);
    const svg = plane.current.getElement()?.querySelector("svg");
    if (svg && s.course != null) svg.style.transform = `rotate(${s.course}deg)`;
  }, [points, t]);

  return null;
}
