// Where incursions cluster: a heatmap of detection locations on a canvas.
// Heavier severities weigh more. Colors run violet → magenta → pink-white,
// so they never look like the severity scale.
import { useEffect, useRef } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import type { Detection } from "../../../api/types";
import { heatWeight } from "../severity";
import { ensurePane } from "./panes";

const PANE = { name: "nfz-heat", z: 380 };

function palette(): Uint8ClampedArray {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 1;
  const ctx = c.getContext("2d")!;
  const g = ctx.createLinearGradient(0, 0, 256, 0);
  g.addColorStop(0, "rgba(76, 29, 149, 0)");
  g.addColorStop(0.25, "rgba(91, 33, 182, 0.55)");
  g.addColorStop(0.5, "rgba(192, 38, 211, 0.75)");
  g.addColorStop(0.75, "rgba(244, 114, 182, 0.85)");
  g.addColorStop(1, "rgba(255, 241, 242, 0.95)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 256, 1);
  return ctx.getImageData(0, 0, 256, 1).data;
}

export function HeatmapLayer({ detections }: { detections: Detection[] }) {
  const map = useLeafletMap();
  const points = useRef<{ lat: number; lon: number; w: number }[]>([]);
  points.current = detections
    .filter((d) => typeof d.latitude === "number" && typeof d.longitude === "number")
    .map((d) => ({ lat: d.latitude as number, lon: d.longitude as number, w: heatWeight(d.severity) }));
  const redrawRef = useRef<() => void>(() => {});

  useEffect(() => {
    if (!map) return;
    const pane = map.getPane(ensurePane(map, PANE))!;
    const canvas = L.DomUtil.create("canvas", "nfz-heat") as HTMLCanvasElement;
    pane.appendChild(canvas);
    const colors = palette();
    const draw = () => {
      const size = map.getSize();
      L.DomUtil.setPosition(canvas, map.containerPointToLayerPoint([0, 0]));
      canvas.width = size.x;
      canvas.height = size.y;
      canvas.style.display = "";
      const ctx = canvas.getContext("2d")!;
      const r = Math.max(14, Math.min(70, 22 * Math.pow(2, (map.getZoom() - 9) / 2)));
      for (const p of points.current) {
        const c = map.latLngToContainerPoint([p.lat, p.lon]);
        if (c.x < -r || c.y < -r || c.x > size.x + r || c.y > size.y + r) continue;
        const g = ctx.createRadialGradient(c.x, c.y, 0, c.x, c.y, r);
        g.addColorStop(0, `rgba(0,0,0,${p.w})`);
        g.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = g;
        ctx.fillRect(c.x - r, c.y - r, 2 * r, 2 * r);
      }
      if (!size.x || !size.y) return;
      const img = ctx.getImageData(0, 0, size.x, size.y);
      const px = img.data;
      for (let i = 3; i < px.length; i += 4) {
        const a = px[i];
        if (!a) continue;
        const j = a * 4;
        px[i - 3] = colors[j];
        px[i - 2] = colors[j + 1];
        px[i - 1] = colors[j + 2];
        px[i] = colors[j + 3];
      }
      ctx.putImageData(img, 0, 0);
    };
    const hide = () => (canvas.style.display = "none");
    redrawRef.current = draw;
    draw();
    map.on("moveend zoomend resize", draw);
    map.on("zoomstart", hide);
    return () => {
      map.off("moveend zoomend resize", draw);
      map.off("zoomstart", hide);
      canvas.remove();
      redrawRef.current = () => {};
    };
  }, [map]);

  const key = detections.map((d) => d.detection_id).join("|");
  useEffect(() => redrawRef.current(), [key]);
  return null;
}
