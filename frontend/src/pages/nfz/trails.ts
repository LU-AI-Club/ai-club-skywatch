// Flight trails. The API only returns each aircraft's newest position, so the
// browser builds trails itself: every time the shared feed refreshes, the new
// positions are appended here. Kept at module level so trails survive
// switching pages.
import type { AircraftFeature } from "../../api/types";
import { nmBetween } from "./geo";
import { altitudeFt } from "./altitude";

/** One recorded position. `alt` is feet (null when unknown). */
export type Fix = { lat: number; lon: number; t: number; alt?: number | null };

export const TRAIL_MINUTES = 15; // how much history each trail keeps
export const MAX_JUMP_NM = 8; // a bigger gap between two fixes breaks the trail

export const trails = new Map<string, Fix[]>();

/** Append the feed's newest positions to `store` and drop old history. */
export function recordFixes(aircraft: AircraftFeature[], store: Map<string, Fix[]> = trails): void {
  let newest = 0;
  for (const a of aircraft) {
    const [lon, lat] = a.geometry.coordinates;
    const t = Date.parse(a.properties.observed_at) || Date.now();
    newest = Math.max(newest, t);
    const list = store.get(a.id) ?? [];
    const last = list[list.length - 1];
    if (!last || (t > last.t && (last.lat !== lat || last.lon !== lon))) {
      list.push({ lat, lon, t, alt: altitudeFt(a.properties.altitude) });
    }
    while (list.length && list[0].t < t - TRAIL_MINUTES * 60_000) list.shift();
    store.set(a.id, list);
  }
  // Forget aircraft that have been gone for a while.
  for (const [id, list] of store) {
    const last = list[list.length - 1];
    if (!last || last.t < newest - 2 * TRAIL_MINUTES * 60_000) store.delete(id);
  }
}

export type TrailRun = { points: [number, number][]; age: 0 | 1 | 2 };

/**
 * Split a trail into drawable runs. Age 0 is the oldest third (drawn
 * dimmest), 2 the newest. A jump bigger than MAX_JUMP_NM (the plane dropped
 * out of the feed and came back) breaks the line instead of drawing across
 * the gap.
 */
export function trailRuns(fixes: Fix[]): TrailRun[] {
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
