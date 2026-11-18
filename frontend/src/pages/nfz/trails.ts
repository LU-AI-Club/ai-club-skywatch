// Flight history. The API only returns each aircraft's newest position, so
// the browser builds history itself: every time the shared feed refreshes,
// the new positions are appended here (and "Load history" in replay can
// backfill from /observations/tracks). Kept at module level so it survives
// switching pages. Trails draw the last few minutes of it; sky replay uses
// up to HISTORY_MINUTES.
import type { AircraftFeature } from "../../api/types";
import { nmBetween } from "./geo";
import { altitudeFt } from "./altitude";

/** One recorded position. `alt` is feet; course/sog when known. */
export type Fix = { lat: number; lon: number; t: number; alt?: number | null; course?: number | null; sog?: number | null };

/** What we remember about an aircraft besides its positions. */
export type AircraftMeta = { icao24: string; callsign: string | null; squawk: string | null; category: string | null };

export const TRAIL_MINUTES = 15; // the longest trail drawn
export const HISTORY_MINUTES = 60; // how much history is kept for replay
export const MAX_JUMP_NM = 8; // a bigger gap between two fixes breaks the trail

export const trails = new Map<string, Fix[]>();
export const aircraftMeta = new Map<string, AircraftMeta>();

/**
 * Trail length to draw for a zoom level. Each zoom step doubles the scale,
 * so halving the minutes keeps a jet's trail around 200 px on screen at any
 * zoom (15 min at zoom 7, 7.5 at 8, ~4 at 9, ~2 at 10, never under 1.5).
 */
export function trailMinutesForZoom(zoom: number | null): number {
  if (zoom == null) return TRAIL_MINUTES;
  return Math.min(TRAIL_MINUTES, Math.max(1.5, TRAIL_MINUTES * Math.pow(2, -(zoom - 7))));
}

/** Append the feed's newest positions to `store` and drop old history. */
export function recordFixes(
  aircraft: AircraftFeature[],
  store: Map<string, Fix[]> = trails,
  meta: Map<string, AircraftMeta> = aircraftMeta,
): void {
  let newest = 0;
  for (const a of aircraft) {
    const p = a.properties;
    const [lon, lat] = a.geometry.coordinates;
    const t = Date.parse(p.observed_at) || Date.now();
    newest = Math.max(newest, t);
    const list = store.get(a.id) ?? [];
    const last = list[list.length - 1];
    if (!last || (t > last.t && (last.lat !== lat || last.lon !== lon))) {
      list.push({ lat, lon, t, alt: altitudeFt(p.altitude), course: p.cog ?? p.heading, sog: p.sog });
    }
    while (list.length && list[0].t < t - HISTORY_MINUTES * 60_000) list.shift();
    store.set(a.id, list);
    meta.set(a.id, { icao24: p.icao24, callsign: p.callsign, squawk: p.squawk, category: p.category });
  }
  // Forget aircraft that have been gone longer than the history window.
  for (const [id, list] of store) {
    const last = list[list.length - 1];
    if (!last || last.t < newest - HISTORY_MINUTES * 60_000) {
      store.delete(id);
      meta.delete(id);
    }
  }
}

export type TrailRun = { points: [number, number][]; age: 0 | 1 | 2 };

/**
 * Split the last `minutes` of a trail (ending at `until`, default the newest
 * fix) into drawable runs. Age 0 is the oldest third (drawn dimmest), 2 the
 * newest. A jump bigger than MAX_JUMP_NM (the plane dropped out of the feed
 * and came back) breaks the line instead of drawing across the gap.
 */
export function trailRuns(all: Fix[], until?: number, minutes: number = TRAIL_MINUTES): TrailRun[] {
  const end = until ?? all[all.length - 1]?.t ?? 0;
  const fixes = all.filter((f) => f.t <= end && f.t > end - minutes * 60_000);
  const runs: TrailRun[] = [];
  let run: [number, number][] = [];
  let age: 0 | 1 | 2 | -1 = -1;
  const flush = () => {
    if (run.length >= 2 && age !== -1) runs.push({ points: run, age });
    run = [];
  };
  for (let i = 1; i < fixes.length; i++) {
    const prev = fixes[i - 1];
    const cur = fixes[i];
    if (nmBetween(prev, cur) > MAX_JUMP_NM) {
      flush();
      age = -1;
      continue;
    }
    const a = Math.min(2, Math.floor((i / fixes.length) * 3)) as 0 | 1 | 2;
    if (a !== age) {
      flush();
      age = a;
    }
    if (!run.length) run.push([prev.lat, prev.lon]);
    run.push([cur.lat, cur.lon]);
  }
  flush();
  return runs;
}

/**
 * Climb (+) or descent (−) rate in feet per minute, from the newest fix and
 * one about a minute older. Null when there isn't enough history.
 */
export function verticalRate(fixes: Fix[], windowMs = 60_000, minSpanMs = 20_000): number | null {
  const last = fixes[fixes.length - 1];
  if (!last || last.alt == null) return null;
  for (const f of fixes) {
    const span = last.t - f.t;
    if (span > windowMs) continue;
    if (span < minSpanMs || f.alt == null) return null;
    return ((last.alt - f.alt) / span) * 60_000;
  }
  return null;
}

/** ↑ climbing, ↓ descending, or "" when level (within ±300 ft/min) or unknown. */
export function trendArrow(rate: number | null): "↑" | "↓" | "" {
  if (rate == null) return "";
  if (rate > 300) return "↑";
  if (rate < -300) return "↓";
  return "";
}
