// Live traffic. Two styles:
//   "lines"  next to a map that draws its own aircraft dots: a trail of where
//            each plane has been plus a small direction pointer.
//   "planes" our own plane icons pointing the way they fly, gliding smoothly
//            between feed updates (dead reckoning from speed and course), ATC
//            data tags with climb/descend arrows, trails, a hover spotlight,
//            lock-on brackets on flagged aircraft, emergency squawks in red,
//            and a selected aircraft (track drawn, optional follow).
// Trails and icons are colored by altitude.
import { useEffect, useRef, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { useObservations } from "../../../api/observations";
import { fetchJSON } from "../../../api/client";
import type { AircraftProperties } from "../../../api/types";
import { altitudeColor, altitudeFt, altitudeTag } from "../altitude";
import { recordFixes, trailRuns, trails, trendArrow, verticalRate } from "../trails";
import { project } from "../geo";
import { parseTrack, type TrackResponse } from "../track";
import { emergencyOf } from "../squawk";
import type { FlaggedAircraft } from "../flagged";
import { ensurePane, PANES } from "./panes";
import { sweepAngle } from "./SweepLayer";
import { useZoom } from "./useZoom";
import { esc } from "./html";

const HEADING_COLOR = "#f4f4f6";
const MIN_MOVING_KNOTS = 40; // slower than this = on the ground: no pointer, no gliding
const MAX_FIX_AGE_HOURS = 0.1; // positions older than ~6 min count as stale (gray)
const MAX_GLIDE_S = 20; // never extrapolate more than this past the last fix
const TAG_MIN_ZOOM = 10; // ATC data tags appear from this zoom (or on hover)
const FADE = [0.15, 0.32, 0.65]; // trail opacity, oldest third → newest

// A small airliner shape, nose pointing up (north) in a 24x24 box.
export const PLANE_PATH =
  "M12 2c.8 0 1.3.9 1.3 2v5.2l7.7 4.6v2l-7.7-2.3v4.6l2.2 1.7V21L12 20.1 8.5 21v-1.2l2.2-1.7v-4.6L3 15.8v-2l7.7-4.6V4c0-1.1.5-2 1.3-2z";

/** @deprecated use FlaggedAircraft from ../flagged */
export type HotAircraft = FlaggedAircraft;

const isStale = (p: AircraftProperties) => !(p.position_age_hours <= MAX_FIX_AGE_HOURS);
export const callsignOf = (p: AircraftProperties) => (p.callsign ?? "").trim() || p.icao24.toUpperCase();

function planeHtml(
  p: AircraftProperties,
  color: string,
  opts: { flag?: { color: string; selected: boolean }; selected: boolean; trend: string },
): string {
  const course = p.cog ?? p.heading;
  const speed = p.sog == null ? "---" : String(Math.round(p.sog));
  const emerg = emergencyOf(p.squawk);
  // Higher planes cast their shadow farther: a small touch of depth.
  const ft = altitudeFt(p.altitude) ?? 0;
  const off = Math.min(9, Math.max(0, ft / 4000)).toFixed(1);
  const glyph =
    course == null
      ? `<i class="nfz-ac-dot"></i>`
      : `<svg class="nfz-ac-shadow" viewBox="0 0 24 24" style="transform:translate(${off}px,${off}px) rotate(${course}deg)"><path d="${PLANE_PATH}"/></svg>` +
        `<svg class="nfz-ac-body" viewBox="0 0 24 24" style="transform:rotate(${course}deg)"><path d="${PLANE_PATH}"/></svg>`;
  const lock = opts.flag
    ? `<span class="nfz-lock${opts.flag.selected ? " is-selected" : ""}" style="--lc:${opts.flag.color}"><i></i><i></i><i></i><i></i></span>`
    : "";
  const cls = ["nfz-ac-inner", opts.flag && "is-hot", opts.selected && "is-picked", emerg && "is-emerg"].filter(Boolean).join(" ");
  return (
    `<div class="${cls}" style="--ac:${emerg ? "#ef4444" : color}">` +
    (opts.selected ? `<span class="nfz-pick"></span>` : "") +
    (emerg ? `<span class="nfz-emerg-ring"></span>` : "") +
    `${lock}${glyph}` +
    `<div class="nfz-tag"><b>${esc(callsignOf(p))}</b><span>${altitudeTag(altitudeFt(p.altitude))}${opts.trend} ${esc(speed)}</span>` +
    (emerg ? `<i>${esc(p.squawk)} ${esc(emerg.toUpperCase())}</i>` : "") +
    `</div></div>`
  );
}

type Motion = { lat: number; lon: number; course: number | null; sog: number | null; t: number; moving: boolean };

export function TrafficLayer({
  mode,
  showPlanes = true,
  showTrails = true,
  showTags = true,
  hot,
  selected = null,
  onSelect,
  follow = false,
  onFollowChange,
  sweep = false,
}: {
  mode: "lines" | "planes";
  showPlanes?: boolean;
  showTrails?: boolean;
  showTags?: boolean;
  hot?: FlaggedAircraft;
  /** Selected aircraft id (ICAO hex), or null. */
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  /** Keep the selected aircraft centered. Dragging the map turns it off. */
  follow?: boolean;
  onFollowChange?: (on: boolean) => void;
  /** Radar sweep running: planes light up as the beam passes them. */
  sweep?: boolean;
}) {
  const map = useLeafletMap();
  const { aircraft } = useObservations();
  const zoom = useZoom(map);
  const [hovered, setHovered] = useState<string | null>(null);
  const planeLayer = useRef<L.LayerGroup | null>(null);
  const markers = useRef(new Map<string, L.Marker>());
  const motion = useRef(new Map<string, Motion>());
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const followRef = useRef({ follow, selected, sweep });
  followRef.current = { follow, selected, sweep };
  const planesOn = mode === "planes" && showPlanes;

  // Data tags for every plane once zoomed in (CSS reads this class).
  useEffect(() => {
    if (!map) return;
    const el = map.getContainer();
    el.classList.toggle("nfz-tags", showTags && (zoom ?? 0) >= TAG_MIN_ZOOM);
    return () => el.classList.remove("nfz-tags");
  }, [map, zoom, showTags]);

  // Spotlight: while a plane is hovered, everything else dims.
  useEffect(() => {
    if (!map) return;
    const el = map.getContainer();
    el.classList.toggle("nfz-spotlight", hovered !== null);
    return () => el.classList.remove("nfz-spotlight");
  }, [map, hovered]);

  // Dragging the map stops following.
  useEffect(() => {
    if (!map || !follow) return;
    const stop = () => onFollowChange?.(false);
    map.on("dragstart", stop);
    return () => {
      map.off("dragstart", stop);
    };
  }, [map, follow, onFollowChange]);

  // Trails (both styles) and direction pointers ("lines" style only).
  useEffect(() => {
    recordFixes(aircraft);
    if (!map) return;
    const pane = ensurePane(map, PANES.trails);
    const renderer = L.canvas({ pane, padding: 0.3 });
    const layer = L.layerGroup().addTo(map);
    const line = { renderer, interactive: false } as const;
    const focus = hovered ?? (mode === "planes" ? selected : null);

    for (const a of aircraft) {
      const p = a.properties;
      const color = emergencyOf(p.squawk) ? "#ef4444" : altitudeColor(altitudeFt(p.altitude), isStale(p));
      const spot = focus === a.id;
      const dim = hovered !== null && !spot ? 0.2 : 1;

      if (showTrails) {
        for (const run of trailRuns(trails.get(a.id) ?? [])) {
          // A soft glow under the newest stretch makes trails read as motion.
          if (run.age === 2 && dim === 1) {
            L.polyline(run.points, { ...line, color, weight: spot ? 9 : 6, opacity: spot ? 0.22 : 0.1 }).addTo(layer);
          }
          L.polyline(run.points, {
            ...line,
            color,
            weight: spot ? 3 : run.age === 2 ? 2 : 1.5,
            opacity: spot ? 0.95 : FADE[run.age] * dim,
          }).addTo(layer);
        }
      }

      // Direction pointer next to a map's own dots: a short line out of the
      // dot with a small arrowhead, sized in screen pixels so it looks the
      // same at every zoom. (Plane icons already point the way they fly.)
      if (mode !== "lines") continue;
      const course = p.cog ?? p.heading;
      if (course == null || p.sog == null || p.sog < MIN_MOVING_KNOTS || isStale(p)) continue;
      const [lon, lat] = a.geometry.coordinates;
      const c = map.latLngToContainerPoint([lat, lon]);
      const rad = (course * Math.PI) / 180;
      const dx = Math.sin(rad); // screen x grows to the right (east)
      const dy = -Math.cos(rad); // screen y grows downward, so north is -y
      const at = (ahead: number, side = 0) =>
        map.containerPointToLatLng(L.point(c.x + dx * ahead - dy * side, c.y + dy * ahead + dx * side));
      const len = Math.min(22, 10 + p.sog / 45);
      L.polyline([at(7), at(len - 4)], { ...line, color: HEADING_COLOR, weight: 1.5, opacity: 0.75 }).addTo(layer);
      L.polygon([at(len), at(len - 5, 3), at(len - 5, -3)], {
        ...line,
        stroke: false,
        fillColor: HEADING_COLOR,
        fillOpacity: 0.9,
      }).addTo(layer);
    }
    return () => {
      layer.remove();
      renderer.remove();
    };
  }, [map, aircraft, mode, showTrails, zoom, hovered, selected]);

  // Plane icons: one marker per aircraft, kept and moved between refreshes
  // (not rebuilt), so hovering survives an update.
  useEffect(() => {
    if (!map || !planesOn) return;
    const layer = L.layerGroup().addTo(map);
    planeLayer.current = layer;
    const ms = markers.current;
    return () => {
      layer.remove();
      planeLayer.current = null;
      ms.clear();
      setHovered(null);
    };
  }, [map, planesOn]);

  useEffect(() => {
    const layer = planeLayer.current;
    if (!map || !layer || !planesOn) return;
    const ms = markers.current;
    const seen = new Set<string>();
    for (const a of aircraft) {
      const p = a.properties;
      const [lon, lat] = a.geometry.coordinates;
      const stale = isStale(p);
      const html = planeHtml(p, altitudeColor(altitudeFt(p.altitude), stale), {
        flag: hot?.get(`icao24:${p.icao24}`),
        selected: selected === a.id,
        trend: trendArrow(verticalRate(trails.get(a.id) ?? [])),
      });
      const t = Date.parse(p.observed_at);
      const course = p.cog ?? p.heading;
      motion.current.set(a.id, {
        lat,
        lon,
        course,
        sog: p.sog,
        t: Number.isFinite(t) ? t : Date.now(),
        moving: !stale && course != null && p.sog != null && p.sog >= MIN_MOVING_KNOTS,
      });
      seen.add(a.id);
      let m = ms.get(a.id);
      if (!m) {
        const id = a.id;
        m = L.marker([lat, lon], {
          keyboard: false,
          riseOnHover: true,
          icon: L.divIcon({ className: "nfz-ac", html, iconSize: [0, 0], iconAnchor: [0, 0] }),
        });
        m.on("mouseover", () => setHovered(id));
        m.on("mouseout", () => setHovered((h) => (h === id ? null : h)));
        m.on("click", () => selectRef.current?.(id));
        m.addTo(layer);
        ms.set(id, m);
      } else {
        m.setLatLng([lat, lon]);
        const el = m.getElement();
        if (el) el.innerHTML = html;
      }
      m.setZIndexOffset(selected === a.id ? 2000 : emergencyOf(p.squawk) ? 1500 : 0);
    }
    for (const [id, m] of ms) {
      if (!seen.has(id)) {
        m.remove();
        ms.delete(id);
        motion.current.delete(id);
      }
    }
  }, [map, aircraft, planesOn, hot, selected]);

  // Glide: between feed updates, move each plane along its course at its
  // speed (capped at MAX_GLIDE_S past its last fix), about 8 times a second.
  // The same tick keeps the selected plane centered in follow mode, draws its
  // velocity vector (where it will be in 1, 2 and 3 minutes), and lights up
  // planes the radar sweep has just passed.
  useEffect(() => {
    if (!map || !planesOn) return;
    let frame = 0;
    let last = 0;
    const vecLayer = L.layerGroup().addTo(map);
    let vecOwner: string | null = null;
    let vecLine: L.Polyline | null = null;
    let vecTicks: L.Polyline[] = [];
    let vecLabels: L.Marker[] = [];
    const clearVec = () => {
      vecLayer.clearLayers();
      vecOwner = null;
      vecLine = null;
      vecTicks = [];
      vecLabels = [];
    };
    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      if (now - last < 120 || document.hidden) return;
      last = now;
      const view = map.getBounds().pad(0.25);
      const wall = Date.now();
      const { follow: following, selected: sel, sweep: sweeping } = followRef.current;
      for (const [id, m] of markers.current) {
        const mo = motion.current.get(id);
        if (!mo || !mo.moving) continue;
        if (!view.contains([mo.lat, mo.lon]) && !(following && id === sel)) continue;
        const dt = Math.min(MAX_GLIDE_S, Math.max(0, (wall - mo.t) / 1000));
        const pos = project(mo, mo.course!, (mo.sog! * dt) / 3600);
        m.setLatLng([pos.lat, pos.lon]);
      }

      // Follow mode: keep the selected plane centered.
      if (following && sel) {
        const fm = markers.current.get(sel);
        if (fm) map.panTo(fm.getLatLng(), { animate: false });
      }

      // Velocity vector for the selected plane.
      const mo = sel ? motion.current.get(sel) : undefined;
      const sm = sel ? markers.current.get(sel) : undefined;
      if (mo && sm && mo.moving) {
        if (vecOwner !== sel) {
          clearVec();
          vecOwner = sel;
          vecLine = L.polyline([], { color: "#f4f4f6", weight: 1.5, opacity: 0.85, dashArray: "5 4", interactive: false }).addTo(vecLayer);
          for (let k = 1; k <= 3; k++) {
            vecTicks.push(L.polyline([], { color: "#f4f4f6", weight: 1.5, opacity: 0.9, interactive: false }).addTo(vecLayer));
            vecLabels.push(
              L.marker([0, 0], {
                interactive: false,
                keyboard: false,
                icon: L.divIcon({ className: "nfz-vec-label", html: `<span>${k}m</span>`, iconSize: [0, 0], iconAnchor: [0, 0] }),
              }).addTo(vecLayer),
            );
          }
        }
        const here = sm.getLatLng();
        const from = { lat: here.lat, lon: here.lng };
        const pts = [1, 2, 3].map((k) => project(from, mo.course!, (mo.sog! * k) / 60));
        vecLine!.setLatLngs([here, ...pts.map((q) => [q.lat, q.lon] as [number, number])]);
        pts.forEach((q, i) => {
          const c = map.latLngToContainerPoint([q.lat, q.lon]);
          const rad = (mo.course! * Math.PI) / 180;
          const nx = Math.cos(rad) * 5; // perpendicular to the course, 5 px each side
          const ny = Math.sin(rad) * 5;
          vecTicks[i].setLatLngs([
            map.containerPointToLatLng(L.point(c.x - nx, c.y - ny)),
            map.containerPointToLatLng(L.point(c.x + nx, c.y + ny)),
          ]);
          vecLabels[i].setLatLng([q.lat, q.lon]);
        });
      } else if (vecOwner) {
        clearVec();
      }

      // Radar paint: brighten planes the sweep has just passed.
      if (sweeping) {
        const size = map.getSize();
        const cx = size.x / 2;
        const cy = size.y / 2;
        const beam = sweepAngle(performance.now());
        for (const m of markers.current.values()) {
          const el = m.getElement();
          if (!el) continue;
          const c = map.latLngToContainerPoint(m.getLatLng());
          if (c.x < -40 || c.y < -40 || c.x > size.x + 40 || c.y > size.y + 40) continue;
          const angle = ((Math.atan2(c.x - cx, cy - c.y) * 180) / Math.PI + 360) % 360;
          const behind = (beam - angle + 360) % 360;
          const lit = behind < 70 ? 1 - behind / 70 : 0;
          el.style.setProperty("--lit", lit.toFixed(2));
        }
      }
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      vecLayer.remove();
      for (const m of markers.current.values()) m.getElement()?.style.removeProperty("--lit");
    };
  }, [map, planesOn]);

  // The selected aircraft's last hour of track, colored by altitude.
  useEffect(() => {
    if (!map || !selected || mode !== "planes") return;
    const controller = new AbortController();
    const layer = L.layerGroup().addTo(map);
    fetchJSON<TrackResponse>("/observations/tracks", { entity_id: selected, lookback_hours: 1 }, controller.signal)
      .then((res) => {
        const pts = parseTrack(res);
        if (pts.length < 2) return;
        const ll = pts.map((q) => [q.lat, q.lon] as [number, number]);
        L.polyline(ll, { color: "#f4f4f6", weight: 8, opacity: 0.1, interactive: false }).addTo(layer);
        // One line per stretch at the same altitude band (not one per fix).
        let start = 0;
        for (let i = 1; i <= pts.length; i++) {
          const color = altitudeColor(pts[Math.min(start + 1, pts.length - 1)].alt);
          if (i < pts.length && altitudeColor(pts[i].alt) === color) continue;
          const seg = ll.slice(start, Math.min(i + 1, ll.length));
          if (seg.length >= 2) L.polyline(seg, { color, weight: 2.5, opacity: 0.95, interactive: false }).addTo(layer);
          start = i;
        }
      })
      .catch(() => {
        /* no track: the strip still shows the aircraft */
      });
    return () => {
      controller.abort();
      layer.remove();
    };
  }, [map, selected, mode]);

  // Clicking empty map clears the selection.
  useEffect(() => {
    if (!map || !onSelect) return;
    const clear = () => {
      if (map.getContainer().classList.contains("nfz-measuring")) return; // measuring, not deselecting
      selectRef.current?.(null);
    };
    map.on("click", clear);
    return () => {
      map.off("click", clear);
    };
  }, [map, onSelect]);

  return null;
}
