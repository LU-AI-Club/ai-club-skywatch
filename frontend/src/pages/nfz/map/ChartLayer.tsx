// Chart decorations for the dashboard map, in the style of a VFR sectional:
//   - a latitude/longitude grid with labels along the edges,
//   - range rings every 10 nm around Lynchburg Regional (KLYH),
//   - a compass rose (true north) around KLYH once you zoom in,
//   - the KLYH airport symbol.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { KLYH, project } from "../geo";
import { gridLabel } from "../format";
import { ensurePane, PANES } from "./panes";
import { useZoom } from "./useZoom";

const GRID_COLOR = "#a8c7ff";
const RING_COLOR = "#cfe3ff";
const RINGS_NM = [10, 20, 30, 40];
const ROSE_NM = 7;
const NM_M = 1852;

/** Grid spacing in degrees for a zoom level. */
function gridStep(zoom: number): number {
  if (zoom <= 6) return 2;
  if (zoom <= 7) return 1;
  if (zoom <= 9) return 0.5;
  if (zoom <= 10) return 1 / 6; // 10'
  return 1 / 12; // 5'
}

function divLabel(latlng: L.LatLngExpression, cls: string, html: string, pane: string) {
  return L.marker(latlng, {
    pane,
    interactive: false,
    keyboard: false,
    icon: L.divIcon({ className: cls, html, iconSize: [0, 0], iconAnchor: [0, 0] }),
  });
}

export function ChartLayer() {
  const map = useLeafletMap();
  const zoom = useZoom(map);
  const [view, setView] = useState(0); // bumps after every pan/zoom

  useEffect(() => {
    if (!map) return;
    // Debounced: follow mode pans the map several times a second.
    let timer: number | undefined;
    const bump = () => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setView((v) => v + 1), 250);
    };
    map.on("moveend", bump);
    return () => {
      window.clearTimeout(timer);
      map.off("moveend", bump);
    };
  }, [map]);

  // Lat/long grid, redrawn for the current view.
  useEffect(() => {
    if (!map || zoom == null) return;
    const pane = ensurePane(map, PANES.chart);
    const labelPane = ensurePane(map, PANES.labels);
    const renderer = L.canvas({ pane, padding: 0.2 });
    const layer = L.layerGroup().addTo(map);
    const b = map.getBounds().pad(0.2);
    const step = gridStep(zoom);
    const style = { renderer, color: GRID_COLOR, weight: 1, opacity: 0.1, interactive: false };
    const top = map.containerPointToLatLng([0, 6]).lat;
    const left = map.containerPointToLatLng([6, 0]).lng;
    // Sectional charts tick every grid line once per minute of arc, with
    // longer ticks every 5' and 10'. Tick lengths are in screen pixels.
    const tickEvery = zoom >= 10 ? 1 / 60 : zoom >= 8 ? 5 / 60 : 0;
    const c0 = map.containerPointToLatLng([0, 0]);
    const c1 = map.containerPointToLatLng([1, 1]);
    const degPerPxLat = Math.abs(c0.lat - c1.lat);
    const degPerPxLon = Math.abs(c1.lng - c0.lng);
    const tickPx = (minute: number) => (minute % 10 === 0 ? 7 : minute % 5 === 0 ? 5 : 3);
    const tickStyle = { renderer, color: GRID_COLOR, weight: 1, opacity: 0.32, interactive: false };
    const minuteOf = (deg: number) => Math.round(Math.abs(deg) * 60) % 60;

    for (let lat = Math.ceil(b.getSouth() / step) * step; lat <= b.getNorth(); lat += step) {
      L.polyline([[lat, b.getWest()], [lat, b.getEast()]], style).addTo(layer);
      divLabel([lat, left], "nfz-grid-label nfz-grid-label--lat", `<span>${gridLabel(lat, "lat")}</span>`, labelPane).addTo(layer);
      if (tickEvery) {
        for (let lon = Math.ceil(b.getWest() / tickEvery) * tickEvery; lon <= b.getEast(); lon += tickEvery) {
          const h = tickPx(minuteOf(lon)) * degPerPxLat;
          L.polyline([[lat - h, lon], [lat + h, lon]], tickStyle).addTo(layer);
        }
      }
    }
    for (let lon = Math.ceil(b.getWest() / step) * step; lon <= b.getEast(); lon += step) {
      L.polyline([[b.getSouth(), lon], [b.getNorth(), lon]], style).addTo(layer);
      divLabel([top, lon], "nfz-grid-label nfz-grid-label--lon", `<span>${gridLabel(lon, "lon")}</span>`, labelPane).addTo(layer);
      if (tickEvery) {
        for (let lat = Math.ceil(b.getSouth() / tickEvery) * tickEvery; lat <= b.getNorth(); lat += tickEvery) {
          const w = tickPx(minuteOf(lat)) * degPerPxLon;
          L.polyline([[lat, lon - w], [lat, lon + w]], tickStyle).addTo(layer);
        }
      }
    }
    return () => {
      layer.remove();
      renderer.remove();
    };
  }, [map, zoom, view]);

  // Range rings, compass rose and the airport symbol.
  useEffect(() => {
    if (!map || zoom == null) return;
    const pane = ensurePane(map, PANES.chart);
    const labelPane = ensurePane(map, PANES.labels);
    const renderer = L.canvas({ pane, padding: 0.3 });
    const layer = L.layerGroup().addTo(map);
    const at = (deg: number, nm: number) => {
      const q = project(KLYH, deg, nm);
      return [q.lat, q.lon] as [number, number];
    };

    for (const nm of RINGS_NM) {
      L.circle([KLYH.lat, KLYH.lon], {
        renderer,
        radius: nm * NM_M,
        color: RING_COLOR,
        weight: 1,
        opacity: 0.16,
        dashArray: "3 6",
        fill: false,
        interactive: false,
      }).addTo(layer);
      if (zoom >= 8) divLabel(at(0, nm), "nfz-ring-label", `<span>${nm} NM</span>`, labelPane).addTo(layer);
    }

    if (zoom >= 9) {
      L.circle([KLYH.lat, KLYH.lon], {
        renderer,
        radius: ROSE_NM * NM_M,
        color: RING_COLOR,
        weight: 1,
        opacity: 0.35,
        fill: false,
        interactive: false,
      }).addTo(layer);
      for (let deg = 0; deg < 360; deg += 5) {
        const len = deg % 30 === 0 ? 1.1 : deg % 10 === 0 ? 0.6 : 0.3;
        L.polyline([at(deg, ROSE_NM), at(deg, ROSE_NM - len)], {
          renderer,
          color: RING_COLOR,
          weight: deg % 30 === 0 ? 1.5 : 1,
          opacity: deg % 30 === 0 ? 0.6 : 0.35,
          interactive: false,
        }).addTo(layer);
        if (deg % 30 === 0) {
          const text = deg === 0 ? "N" : deg === 90 ? "E" : deg === 180 ? "S" : deg === 270 ? "W" : String(deg / 10);
          divLabel(at(deg, ROSE_NM + 0.9), "nfz-rose-label", `<span>${text}</span>`, labelPane).addTo(layer);
        }
      }
    }

    // KLYH: a towered airport (blue on sectionals), runway 04/22.
    divLabel(
      [KLYH.lat, KLYH.lon],
      "nfz-airport",
      `<svg viewBox="-12 -12 24 24" aria-hidden="true"><circle r="7"/><path d="M0 -7V-10M7 0H10M0 7V10M-7 0H-10"/>` +
        `<path class="rwy" d="M-3.9 4.6L3.9 -4.6"/></svg><span>KLYH</span>`,
      labelPane,
    ).addTo(layer);

    return () => {
      layer.remove();
      renderer.remove();
    };
  }, [map, zoom]);

  return null;
}
