// One aircraft's recorded track (from GET /observations/tracks), and how to
// read a position off it at any moment (used by the replay).
import { altitudeFt } from "./altitude";

export type TrackPoint = {
  t: number; // ms since epoch
  lat: number;
  lon: number;
  alt: number | null; // feet
  sog: number | null; // knots
  course: number | null; // degrees
};

export type TrackResponse = {
  geometry?: { coordinates?: [number, number][] };
  properties?: { points?: Record<string, unknown>[] };
};

const n = (v: unknown): number | null => {
  const x = Number(v);
  return v == null || v === "" || !Number.isFinite(x) ? null : x;
};

/** Turn the API response into sorted points, skipping unusable ones. */
export function parseTrack(res: TrackResponse): TrackPoint[] {
  const raw = res.properties?.points ?? [];
  const coords = res.geometry?.coordinates ?? [];
  const pts: TrackPoint[] = [];
  raw.forEach((p, i) => {
    const t = Date.parse(String(p.observed_at ?? ""));
    const lat = n(p.latitude) ?? coords[i]?.[1] ?? null;
    const lon = n(p.longitude) ?? coords[i]?.[0] ?? null;
    if (!Number.isFinite(t) || lat == null || lon == null) return;
    pts.push({ t, lat, lon, alt: altitudeFt(p.altitude), sog: n(p.sog), course: n(p.cog) ?? n(p.heading) });
  });
  return pts.sort((a, b) => a.t - b.t);
}

/** Keep the part of a track around an incursion (with some lead-in and lead-out). */
export function windowTrack(points: TrackPoint[], start: number, end: number, padMs = 15 * 60_000): TrackPoint[] {
  const w = points.filter((p) => p.t >= start - padMs && p.t <= end + padMs);
  return w.length >= 2 ? w : points;
}

function lerp(a: number, b: number, f: number) {
  return a + (b - a) * f;
}

/** Bearing from one point to the next, in degrees (flat-earth). */
export function bearing(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const dx = (b.lon - a.lon) * Math.cos((a.lat * Math.PI) / 180);
  const dy = b.lat - a.lat;
  return ((Math.atan2(dx, dy) * 180) / Math.PI + 360) % 360;
}

export type TrackSample = TrackPoint & { index: number };

/** Position, altitude and course at time t, interpolated between recorded fixes. */
export function sampleTrack(points: TrackPoint[], t: number): TrackSample | null {
  if (!points.length) return null;
  if (t <= points[0].t) return { ...points[0], index: 0 };
  const last = points.length - 1;
  if (t >= points[last].t) return { ...points[last], index: last };
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (points[mid].t <= t) lo = mid;
    else hi = mid;
  }
  const a = points[lo];
  const b = points[hi];
  const f = (t - a.t) / (b.t - a.t || 1);
  return {
    t,
    lat: lerp(a.lat, b.lat, f),
    lon: lerp(a.lon, b.lon, f),
    alt: a.alt != null && b.alt != null ? lerp(a.alt, b.alt, f) : (a.alt ?? b.alt),
    sog: a.sog ?? b.sog,
    course: a.course ?? bearing(a, b),
    index: lo,
  };
}
