// The airspace zones, drawn like a sectional chart: a diagonal hatch fill,
// a crisp outline, tick marks along the border, and labels with the zone's
// floor and ceiling. Zones with incursions glow; the selected zone gets a
// white outline.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import type { Detection } from "../../../api/types";
import { useZoneFiles, zoneClass, zoneColor, toZones, altitudeRange, scheduleLabel } from "../zones";
import { limitLabel } from "../altitude";
import { ensureHatchDefs } from "./svgDefs";
import { ensurePane, PANES } from "./panes";
import { useZoom } from "./useZoom";
import { esc } from "./html";

const MOA_LABEL_MIN_ZOOM = 9; // MOA names appear once you zoom in a little
const ALT_LABEL_MIN_ZOOM = 9; // floor/ceiling under each label

type Box = { x: number; y: number; w: number; h: number };
const overlaps = (a: Box, b: Box) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;

export function ZoneLayer({
  detections,
  focusZoneId,
  onZoneClick,
}: {
  detections: Detection[];
  focusZoneId?: string | null;
  onZoneClick?: (zoneId: string) => void;
}) {
  const map = useLeafletMap();
  const files = useZoneFiles();
  const zoom = useZoom(map);

  useEffect(() => {
    if (!map) return;
    ensureHatchDefs();
    const labelPane = ensurePane(map, PANES.labels);
    const layer = L.layerGroup().addTo(map);
    const hotZones = new Set(detections.map((d) => String(d.zone_id ?? "")));
    const labelled = new Set<string>();
    const placed: Box[] = [];
    const infoById = new Map(toZones(files).map((z) => [z.id, z]));

    for (const fc of files) {
      for (const f of fc.features ?? []) {
        const p = f.properties ?? {};
        const id = String(p.zone_id ?? "");
        const info = infoById.get(id);
        const hot = hotZones.has(id);
        const focus = !!focusZoneId && focusZoneId === id;
        const cls = zoneClass(p.zone_type);
        const color = zoneColor(p.zone_type);

        // Glow under zones with incursions (CSS blurs and pulses it).
        if (hot) {
          L.geoJSON(f as never, {
            interactive: false,
            style: { color, weight: 12, opacity: 0.35, fill: false, className: "nfz-zglow" },
          }).addTo(layer);
        }
        // Tick marks along the border.
        L.geoJSON(f as never, {
          interactive: false,
          style: {
            color,
            weight: hot ? 9 : 7,
            opacity: hot ? 0.75 : 0.45,
            dashArray: "2 5",
            lineCap: "butt",
            fill: false,
          },
        }).addTo(layer);
        // Hatched fill + crisp outline (CSS swaps the fill for a hatch pattern).
        const shape = L.geoJSON(f as never, {
          style: {
            color: focus ? "#f4f4f6" : color,
            weight: focus ? 2.5 : hot ? 2.2 : 1.4,
            opacity: 1,
            fillColor: color,
            fillOpacity: 0.08,
            className: `nfz-zfill nfz-zfill--${cls}${hot ? " is-hot" : ""}${focus ? " is-focus" : ""}`,
          },
          onEachFeature: (_feat, l) => {
            const range = info ? altitudeRange(info) : "";
            const sched = info ? scheduleLabel(info.activation) : "";
            l.bindTooltip(
              `<b>${esc(p.name ?? id)}</b><span class="nfz-tip-type nfz-tip-type--${cls}">${esc(p.zone_type)}</span>` +
                `<div>${esc(range)}${sched ? ` · ${esc(sched)}` : ""}</div>` +
                (onZoneClick ? `<div class="nfz-tip-hint">click for zone details</div>` : ""),
              { sticky: true, className: "nfz-tip", direction: "top", offset: [0, -8] },
            );
            if (onZoneClick) l.on("click", () => onZoneClick(id));
          },
        }).addTo(layer);

        // One label per zone name. Prohibited and restricted zones are small,
        // so they always get a diamond at their center with the name above it
        // (that is how you find P-56 when zoomed out); MOA names are plain
        // text and wait until you zoom in. Labels that would overlap one
        // already placed are stacked upward instead.
        const isMoa = cls === "moa";
        const text = isMoa ? String(p.name ?? id) : id.replace(/\s*#\d+$/, "");
        if (labelled.has(text)) continue;
        if (isMoa && (zoom ?? 0) < MOA_LABEL_MIN_ZOOM) continue;
        labelled.add(text);
        const bounds = shape.getBounds();
        if (!bounds.isValid()) continue;
        const center = bounds.getCenter();
        // Limits printed like a chart: ceiling over floor.
        const showLimits = !!info && (zoom ?? 0) >= ALT_LABEL_MIN_ZOOM;
        const ceil = info ? limitLabel(info.ceilingFt, info.ceilingDatum) : "";
        const floor = info ? limitLabel(info.floorFt, info.floorDatum) : "";
        const w = Math.max(text.length * (isMoa ? 7.4 : 6.9), Math.max(ceil.length, floor.length) * 6.4) + 10;
        const h = showLimits ? 42 : 15;
        const pt = map.latLngToContainerPoint(center);
        const box = { x: pt.x - w / 2, y: isMoa ? pt.y - h / 2 : pt.y - 14 - h, w, h };
        let dy = 0;
        for (let tries = 0; tries < 8 && placed.some((b) => overlaps(b, { ...box, y: box.y + dy })); tries++) dy -= h + 2;
        placed.push({ ...box, y: box.y + dy });
        const shift = isMoa ? `translate(-50%, calc(-50% + ${dy}px))` : `translate(-50%, calc(-100% - 14px + ${dy}px))`;
        L.marker(center, {
          pane: labelPane,
          interactive: false,
          keyboard: false,
          icon: L.divIcon({
            className: `nfz-ml nfz-ml--${cls}${hot ? " is-hot" : ""}${isMoa ? " is-text" : ""}`,
            html:
              (isMoa ? "" : `<i class="nfz-ml-dia"></i>`) +
              `<span class="nfz-ml-text" style="transform:${shift}">${esc(text)}` +
              (showLimits ? `<span class="nfz-frac"><b>${esc(ceil)}</b><b>${esc(floor)}</b></span>` : "") +
              `</span>`,
            iconSize: [0, 0],
            iconAnchor: [0, 0],
          }),
        }).addTo(layer);
      }
    }
    return () => {
      layer.remove();
    };
  }, [map, files, detections, zoom, focusZoneId, onZoneClick]);

  return null;
}
