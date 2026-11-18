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
import type { AircraftFeature, AircraftProperties } from "../../../api/types";
import { altitudeColor, altitudeFt, altitudeTag } from "../altitude";
import { recordFixes, trailMinutesForZoom, trailRuns, trails, trendArrow, verticalRate, type Fix } from "../trails";
import { useThrottled } from "../hooks/useThrottled";
import { project } from "../geo";
import { parseTrack, type TrackResponse } from "../track";
import { emergencyOf } from "../squawk";
import type { FlaggedAircraft } from "../flagged";
import { ensurePane, PANES } from "./panes";
import { sweepAngle } from "./SweepLayer";
import { placeTags, tagSize, type Slot, type TagRequest } from "./labels";
import type { TagMode } from "./LayerSwitch";
import { useZoom } from "./useZoom";
import { esc } from "./html";

const HEADING_COLOR = "#f4f4f6";
const MIN_MOVING_KNOTS = 40; // slower than this = on the ground: no pointer, no gliding
const MAX_FIX_AGE_HOURS = 0.1; // positions older than ~6 min count as stale (gray)
const MAX_GLIDE_S = 20; // never extrapolate more than this past the last fix
const TAG_MIN_ZOOM = 10; // ATC data tags appear from this zoom (or on hover)
const LOW_FT = 5_000; // "key" tags: aircraft below this are shown
const HIGH_FT = 18_000; // above every zone's ceiling: drawn dimmer
const FADE = [0.15, 0.32, 0.65]; // trail opacity, oldest third → newest

// A small airliner shape, nose pointing up (north) in a 24x24 box.
export const PLANE_PATH =
  "M12 2c.8 0 1.3.9 1.3 2v5.2l7.7 4.6v2l-7.7-2.3v4.6l2.2 1.7V21L12 20.1 8.5 21v-1.2l2.2-1.7v-4.6L3 15.8v-2l7.7-4.6V4c0-1.1.5-2 1.3-2z";

/** @deprecated use FlaggedAircraft from ../flagged */
export type HotAircraft = FlaggedAircraft;

const isStale = (p: AircraftProperties) => !(p.position_age_hours <= MAX_FIX_AGE_HOURS);
/** History up to a replay moment (all of it when live). */
const upTo = (fixes: Fix[], at: number | null) => (at == null ? fixes : fixes.filter((f) => f.t <= at));
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
  const band = ft > 0 && ft < LOW_FT ? "is-low" : ft > HIGH_FT ? "is-high" : "";
  const cls = ["nfz-ac-inner", band, opts.flag && "is-hot", opts.selected && "is-picked", emerg && "is-emerg"].filter(Boolean).join(" ");
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
  tagMode = "key",
  hot,
  selected = null,
  onSelect,
  follow = false,
  onFollowChange,
  sweep = false,
  aircraft: aircraftProp,
  replayAt = null,
}: {
  mode: "lines" | "planes";
  showPlanes?: boolean;
  showTrails?: boolean;
  /** Which aircraft get data tags when zoomed in. */
  tagMode?: TagMode;
  hot?: FlaggedAircraft;
  /** Selected aircraft id (ICAO hex), or null. */
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  /** Keep the selected aircraft centered. Dragging the map turns it off. */
  follow?: boolean;
  onFollowChange?: (on: boolean) => void;
  /** Radar sweep running: planes light up as the beam passes them. */
  sweep?: boolean;
  /** Aircraft to draw (sky replay passes past positions); default = the live feed. */
  aircraft?: AircraftFeature[];
  /** Sky replay moment (ms), or null for live. */
  replayAt?: number | null;
}) {
  const map = useLeafletMap();
  const { aircraft: live } = useObservations();
  const aircraft = aircraftProp ?? live;
  const zoom = useZoom(map);
  // Trails redraw at most twice a second during replay.
  const trailAircraft = useThrottled(aircraft, replayAt != null ? 500 : 0);
  const trailAt = useThrottled(replayAt, replayAt != null ? 500 : 0);

  // Always record the live feed (history keeps building during replay too).
  useEffect(() => {
    recordFixes(live);
  }, [live]);
  const [hovered, setHovered] = useState<string | null>(null);
  const planeLayer = useRef<L.LayerGroup | null>(null);
  const markers = useRef(new Map<string, L.Marker>());
  const motion = useRef(new Map<string, Motion>());
  const htmlCache = useRef(new Map<string, string>());
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const followRef = useRef({ follow, selected, sweep });
  followRef.current = { follow, selected, sweep };
  const planesOn = mode === "planes" && showPlanes;

  // Data tags once zoomed in (CSS reads these classes): "key" shows low and
  // important aircraft, "all" shows everyone.
  useEffect(() => {
    if (!map) return;
    const el = map.getContainer();
    const on = tagMode !== "off" && (zoom ?? 0) >= TAG_MIN_ZOOM;
    el.classList.toggle("nfz-tags", on);
    el.classList.toggle("nfz-tags-all", on && tagMode === "all");
    return () => el.classList.remove("nfz-tags", "nfz-tags-all");
  }, [map, zoom, tagMode]);

  // Zoom bands for CSS: far = simplified planes, near = full detail (blurred shadows).
  useEffect(() => {
    if (!map) return;
    const el = map.getContainer();
    el.classList.toggle("nfz-far", (zoom ?? 9) <= 7);
    el.classList.toggle("nfz-near", (zoom ?? 0) >= 10);
    return () => el.classList.remove("nfz-far", "nfz-near");
  }, [map, zoom]);

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
    if (!map) return;
    const minutes = trailMinutesForZoom(zoom);
    const pane = ensurePane(map, PANES.trails);
    const renderer = L.canvas({ pane, padding: 0.3 });
    const layer = L.layerGroup().addTo(map);
    const line = { renderer, interactive: false } as const;
    const focus = hovered ?? (mode === "planes" ? selected : null);

    for (const a of trailAircraft) {
      const p = a.properties;
      const color = emergencyOf(p.squawk) ? "#ef4444" : altitudeColor(altitudeFt(p.altitude), isStale(p));
      const spot = focus === a.id;
      // High traffic (above every zone) gets fainter trails to keep the map calm.
      const high = (altitudeFt(p.altitude) ?? 0) > HIGH_FT && !hot?.has(`icao24:${p.icao24}`);
      const dim = (hovered !== null && !spot ? 0.2 : 1) * (high && !spot ? 0.4 : 1);

      if (showTrails) {
        for (const run of trailRuns(trails.get(a.id) ?? [], trailAt ?? undefined, minutes)) {
          // A soft glow under the newest stretch makes trails read as motion.
          if (run.age === 2 && dim === 1 && !high) {
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
  }, [map, trailAircraft, trailAt, mode, showTrails, zoom, hovered, selected, hot]);

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
      htmlCache.current.clear();
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
        trend: trendArrow(verticalRate(upTo(trails.get(a.id) ?? [], replayAt))),
      });
      const t = Date.parse(p.observed_at);
      const course = p.cog ?? p.heading;
      motion.current.set(a.id, {
        lat,
        lon,
        course,
        sog: p.sog,
        t: Number.isFinite(t) ? t : Date.now(),
        // No gliding in replay: positions come from the replay clock.
        moving: replayAt == null && !stale && course != null && p.sog != null && p.sog >= MIN_MOVING_KNOTS,
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
        // Only rebuild the icon when it actually looks different.
        if (htmlCache.current.get(a.id) !== html) {
          const el = m.getElement();
          if (el) el.innerHTML = html;
        }
      }
      htmlCache.current.set(a.id, html);
      m.setZIndexOffset(selected === a.id ? 2000 : emergencyOf(p.squawk) ? 1500 : 0);
    }
    for (const [id, m] of ms) {
      if (!seen.has(id)) {
        m.remove();
        ms.delete(id);
        motion.current.delete(id);
        htmlCache.current.delete(id);
      }
    }
  }, [map, aircraft, planesOn, hot, selected, replayAt]);

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
    const litState = new Map<string, number>();
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
      // Only planes whose glow actually changed are touched, and the glow
      // filter is switched on (class is-lit) only while a plane is lit.
      if (sweeping) {
        const size = map.getSize();
        const cx = size.x / 2;
        const cy = size.y / 2;
        const beam = sweepAngle(performance.now());
        for (const [id, m] of markers.current) {
          const el = m.getElement();
          if (!el) continue;
          const c = map.latLngToContainerPoint(m.getLatLng());
          if (c.x < -40 || c.y < -40 || c.x > size.x + 40 || c.y > size.y + 40) continue;
          const angle = ((Math.atan2(c.x - cx, cy - c.y) * 180) / Math.PI + 360) % 360;
          const behind = (beam - angle + 360) % 360;
          const lit = behind < 70 ? Math.round((1 - behind / 70) * 20) / 20 : 0;
          const prev = litState.get(id) ?? 0;
          if (lit === prev) continue;
          litState.set(id, lit);
          if (lit > 0) {
            el.style.setProperty("--lit", String(lit));
            if (!prev) el.classList.add("is-lit");
          } else {
            el.style.removeProperty("--lit");
            el.classList.remove("is-lit");
          }
        }
      }
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      vecLayer.remove();
      for (const m of markers.current.values()) {
        const el = m.getElement();
        el?.style.removeProperty("--lit");
        el?.classList.remove("is-lit");
      }
    };
  }, [map, planesOn]);

  // Data-tag placement: about once a second, plus after every pan/zoom and
  // feed update. Only runs while tags are showing.
  const hotRef = useRef(hot);
  hotRef.current = hot;
  useEffect(() => {
    if (!map || !planesOn) return;
    const slots = new Map<string, Slot>();
    const layout = () => {
      const box = map.getContainer();
      if (!box.classList.contains("nfz-tags")) return;
      const all = box.classList.contains("nfz-tags-all");
      const size = map.getSize();
      const reqs: TagRequest[] = [];
      for (const [id, m] of markers.current) {
        const el = m.getElement();
        if (!el) continue;
        const c = map.latLngToContainerPoint(m.getLatLng());
        if (c.x < -60 || c.y < -60 || c.x > size.x + 60 || c.y > size.y + 60) continue;
        const inner = el.firstElementChild as HTMLElement | null;
        const call = inner?.querySelector(".nfz-tag b")?.textContent ?? "";
        const emerg = !!inner?.classList.contains("is-emerg");
        const flagged = !!inner?.classList.contains("is-hot");
        const picked = id === followRef.current.selected;
        const low = !!inner?.classList.contains("is-low");
        if (!(all || low || emerg || flagged || picked)) continue; // this tag isn't showing
        const altText = inner?.querySelector(".nfz-tag span")?.textContent ?? "";
        const alt = parseInt(altText, 10);
        const { w, h } = tagSize(call, emerg ? 3 : 2);
        reqs.push({
          id,
          x: c.x,
          y: c.y,
          w,
          h,
          force: picked || emerg || flagged,
          // selected > emergency > flagged > lower altitude first
          priority: (picked ? 4000 : 0) + (emerg ? 3000 : 0) + (flagged ? 2000 : 0) + (Number.isFinite(alt) ? 1000 - Math.min(999, alt) : 0),
          prev: slots.get(id),
        });
      }
      const result = placeTags(reqs);
      for (const [id, slot] of result) {
        if (slots.get(id) === slot) continue;
        slots.set(id, slot);
        markers.current.get(id)?.getElement()?.setAttribute("data-slot", slot);
      }
    };
    const timer = window.setInterval(layout, 1000);
    map.on("moveend zoomend", layout);
    const first = window.setTimeout(layout, 50);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(first);
      map.off("moveend zoomend", layout);
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
