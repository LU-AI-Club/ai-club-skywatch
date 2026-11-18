// Sky replay: where every aircraft was at a past moment, from the recorded
// history in trails.ts. Pure functions, so they're easy to test.
import type { AircraftFeature } from "../../api/types";
import { bearing } from "./track";
import { nmBetween } from "./geo";
import { MAX_JUMP_NM, type AircraftMeta, type Fix } from "./trails";
import type { TrackPoint } from "./track";

const STALE_AFTER_MS = 45_000; // past the last fix, an aircraft drops out of the replay

/** Every aircraft that has a recorded position around time t, interpolated. */
export function aircraftAt(store: Map<string, Fix[]>, meta: Map<string, AircraftMeta>, t: number): AircraftFeature[] {
  const out: AircraftFeature[] = [];
  for (const [id, fixes] of store) {
    if (!fixes.length || t < fixes[0].t || t > fixes[fixes.length - 1].t + STALE_AFTER_MS) continue;
    // Binary search for the last fix at or before t.
    let lo = 0;
    let hi = fixes.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (fixes[mid].t <= t) lo = mid;
      else hi = mid - 1;
    }
    const a = fixes[lo];
    const b = fixes[lo + 1];
    let lat = a.lat;
    let lon = a.lon;
    let alt = a.alt ?? null;
    let course = a.course ?? null;
    let sog = a.sog ?? null;
    if (b && nmBetween(a, b) <= MAX_JUMP_NM && b.t - a.t <= 5 * 60_000) {
      const f = (t - a.t) / (b.t - a.t || 1);
      lat = a.lat + (b.lat - a.lat) * f;
      lon = a.lon + (b.lon - a.lon) * f;
      if (a.alt != null && b.alt != null) alt = a.alt + (b.alt - a.alt) * f;
      if (nmBetween(a, b) > 0.05) course = bearing(a, b);
      if (sog == null) sog = (nmBetween(a, b) / ((b.t - a.t) / 3_600_000)) || null;
    } else if (t - a.t > STALE_AFTER_MS) {
      continue;
    }
    const m = meta.get(id);
    out.push({
      type: "Feature",
      id,
      geometry: { type: "Point", coordinates: [lon, lat] },
      properties: {
        icao24: m?.icao24 ?? id,
        callsign: m?.callsign ?? null,
        altitude: alt == null ? null : alt <= 0 ? "ground" : String(Math.round(alt)),
        squawk: m?.squawk ?? null,
        category: m?.category ?? null,
        sog,
        cog: course,
        heading: course,
        latitude: lat,
        longitude: lon,
        observed_at: new Date(t).toISOString(),
        position_age_hours: Math.max(0, t - a.t) / 3_600_000,
        source_id: "replay",
      },
    });
  }
  return out;
}

/** Earliest recorded moment across all aircraft (null when empty). */
export function historyStart(store: Map<string, Fix[]>): number | null {
  let min = Infinity;
  for (const f of store.values()) if (f.length && f[0].t < min) min = f[0].t;
  return Number.isFinite(min) ? min : null;
}

/**
 * Merge a fetched track into the store: thinned to one fix per `stepMs`,
 * sorted, and without duplicating fixes we already have.
 */
export function mergeTrack(store: Map<string, Fix[]>, id: string, points: TrackPoint[], stepMs = 10_000, keepAfter = 0): number {
  const existing = store.get(id) ?? [];
  const have = new Set(existing.map((f) => Math.round(f.t / 1000)));
  const added: Fix[] = [];
  let lastT = -Infinity;
  for (const p of points) {
    if (p.t < keepAfter || p.t - lastT < stepMs || have.has(Math.round(p.t / 1000))) continue;
    added.push({ lat: p.lat, lon: p.lon, t: p.t, alt: p.alt, course: p.course, sog: p.sog });
    lastT = p.t;
  }
  if (!added.length) return 0;
  const merged = [...existing, ...added].sort((x, y) => x.t - y.t);
  store.set(id, merged);
  return added.length;
}
