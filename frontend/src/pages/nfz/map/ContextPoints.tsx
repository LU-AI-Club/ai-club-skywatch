// Airports and navaids, drawn small and quiet in sectional-chart symbols.
// Only what's in view is drawn, and the smaller things wait for closer zoom:
//   airports: large/medium from zoom 8 (names from 9), small from zoom 10;
//   navaids:  VOR family from zoom 8, NDBs from zoom 9; labels from 9.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { useZoom } from "./useZoom";
import { ensurePane, PANES } from "./panes";
import { esc } from "./html";
import { loadContext, type PointCollection, type PointFeature } from "./contextData";

function airportSvg(kind: string): string {
  // Large/medium: circle with four ticks (like a towered field on a chart).
  if (kind === "large" || kind === "medium") {
    return `<svg viewBox="-10 -10 20 20"><circle r="5.5"/><path d="M0 -5.5V-8.5M5.5 0H8.5M0 5.5V8.5M-5.5 0H-8.5"/></svg>`;
  }
  return `<svg viewBox="-10 -10 20 20"><circle r="3.6"/></svg>`;
}

function navaidSvg(kind: string): string {
  const hex = "M-3.5 -6H3.5L7 0L3.5 6H-3.5L-7 0Z";
  if (kind === "VORTAC") {
    return `<svg viewBox="-12 -12 24 24"><path d="${hex}"/><path class="ear" d="M-3.5 -6H3.5L4.6 -8H-4.6Z M7 0L3.5 6L4.6 8L9.2 0Z M-7 0L-3.5 6L-4.6 8L-9.2 0Z"/></svg>`;
  }
  if (kind === "VOR-DME") return `<svg viewBox="-12 -12 24 24"><rect x="-8" y="-7" width="16" height="14"/><path d="${hex}"/></svg>`;
  if (kind === "VOR") return `<svg viewBox="-12 -12 24 24"><path d="${hex}"/><circle class="dot" r="1"/></svg>`;
  // NDB: a stippled ring, as on sectionals.
  return `<svg viewBox="-12 -12 24 24"><circle class="ndb" r="6"/><circle class="dot" r="1.4"/></svg>`;
}

function useContext(name: "airports" | "navaids"): PointCollection | null {
  const [data, setData] = useState<PointCollection | null>(null);
  useEffect(() => {
    let cancelled = false;
    loadContext(name)
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setData(null));
    return () => {
      cancelled = true;
    };
  }, [name]);
  return data;
}

function useViewTick(map: L.Map | null): number {
  const [n, setN] = useState(0);
  useEffect(() => {
    if (!map) return;
    let t: number | undefined;
    const bump = () => {
      window.clearTimeout(t);
      t = window.setTimeout(() => setN((x) => x + 1), 150);
    };
    map.on("moveend", bump);
    return () => {
      window.clearTimeout(t);
      map.off("moveend", bump);
    };
  }, [map]);
  return n;
}

function drawPoints(
  map: L.Map,
  features: PointFeature[],
  keep: (f: PointFeature) => boolean,
  html: (f: PointFeature) => string,
  tip: (f: PointFeature) => string,
  cls: (f: PointFeature) => string,
): L.LayerGroup {
  const pane = ensurePane(map, PANES.labels);
  const layer = L.layerGroup().addTo(map);
  const view = map.getBounds().pad(0.15);
  for (const f of features) {
    const [lon, lat] = f.geometry.coordinates;
    if (!view.contains([lat, lon]) || !keep(f)) continue;
    L.marker([lat, lon], {
      pane,
      keyboard: false,
      icon: L.divIcon({ className: cls(f), html: html(f), iconSize: [0, 0], iconAnchor: [0, 0] }),
    })
      .bindTooltip(tip(f), { className: "nfz-tip", direction: "top", offset: [0, -8] })
      .addTo(layer);
  }
  return layer;
}

export function AirportsLayer({ skip = [] }: { skip?: string[] }) {
  const map = useLeafletMap();
  const zoom = useZoom(map);
  const tick = useViewTick(map);
  const data = useContext("airports");
  useEffect(() => {
    if (!map || !data || zoom == null || zoom < 8) return;
    const layer = drawPoints(
      map,
      data.features,
      (f) => {
        const kind = String(f.properties.kind);
        if (skip.includes(String(f.properties.ident))) return false;
        return kind === "small" ? zoom >= 10 : true;
      },
      (f) => {
        const kind = String(f.properties.kind);
        const showName = kind === "small" ? zoom >= 11 : zoom >= 9;
        return airportSvg(kind) + (showName ? `<span>${esc(f.properties.ident)}</span>` : "");
      },
      (f) =>
        `<b>${esc(f.properties.ident)}</b> ${esc(f.properties.name)}` +
        `<div>${f.properties.city ? `${esc(f.properties.city)} · ` : ""}elev ${esc(f.properties.elev_ft ?? "—")} ft</div>`,
      (f) => `nfz-apt nfz-apt--${String(f.properties.kind)}`,
    );
    return () => {
      layer.remove();
    };
  }, [map, data, zoom, tick, skip.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function NavaidsLayer() {
  const map = useLeafletMap();
  const zoom = useZoom(map);
  const tick = useViewTick(map);
  const data = useContext("navaids");
  useEffect(() => {
    if (!map || !data || zoom == null || zoom < 8) return;
    const layer = drawPoints(
      map,
      data.features,
      (f) => (String(f.properties.kind).startsWith("NDB") ? zoom >= 9 : true),
      (f) =>
        navaidSvg(String(f.properties.kind)) +
        (zoom >= 9 ? `<span><b>${esc(f.properties.ident)}</b> ${esc(f.properties.freq ?? "")}</span>` : ""),
      (f) => `<b>${esc(f.properties.ident)}</b> ${esc(f.properties.name)} ${esc(f.properties.kind)}<div>${esc(f.properties.freq ?? "—")}${String(f.properties.kind).startsWith("NDB") ? " kHz" : " MHz"}</div>`,
      (f) => `nfz-nav nfz-nav--${String(f.properties.kind).startsWith("NDB") ? "ndb" : "vor"}`,
    );
    return () => {
      layer.remove();
    };
  }, [map, data, zoom, tick]);
  return null;
}
