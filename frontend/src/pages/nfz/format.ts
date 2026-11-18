// Time and number formatting for the NFZ page. Aviation runs on UTC ("Zulu")
// time, so every clock time on the page is Zulu.

export const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
export const pad2 = (n: number) => String(n).padStart(2, "0");

export function toDate(v: unknown): Date | null {
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v;
  if (typeof v !== "string" && typeof v !== "number") return null;
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** "17 NOV 21:42:05Z" */
export function zuluTime(v: unknown): string {
  const d = toDate(v);
  if (!d) return "—";
  return `${pad2(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]} ${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}Z`;
}

/** "21:42Z" */
export function zuluShort(v: unknown): string {
  const d = toDate(v);
  return d ? `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}Z` : "—";
}

/** "21:42:05Z" */
export function zuluClock(v: unknown): string {
  const d = toDate(v);
  return d ? `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())}Z` : "—";
}

/** "17 NOV" */
export function zuluDay(v: unknown): string {
  const d = toDate(v);
  return d ? `${pad2(d.getUTCDate())} ${MONTHS[d.getUTCMonth()]}` : "—";
}

/** "20261117T2142Z", for file names. */
export function zuluStamp(v: unknown): string {
  const d = toDate(v);
  if (!d) return "unknown";
  return `${d.getUTCFullYear()}${pad2(d.getUTCMonth() + 1)}${pad2(d.getUTCDate())}T${pad2(d.getUTCHours())}${pad2(d.getUTCMinutes())}Z`;
}

/** "45s ago", "3 min ago", "2 h ago", "4 d ago". `now` is injectable for tests. */
export function ago(v: unknown, now: number = Date.now()): string {
  const d = toDate(v);
  if (!d) return "—";
  const s = Math.max(0, Math.round((now - d.getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

/** Seconds as "42 s" or "4 m 37 s". */
export function duration(v: unknown): string {
  const s = Number(v);
  if (v === null || v === undefined || v === "" || !Number.isFinite(s)) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  return `${m} m ${Math.round(s % 60)} s`;
}

/** Degrees as a chart-style coordinate: 37°19'36"N, 079°12'04"W. */
export function dms(value: number, axis: "lat" | "lon"): string {
  const hemi = axis === "lat" ? (value >= 0 ? "N" : "S") : value >= 0 ? "E" : "W";
  let a = Math.abs(value);
  let deg = Math.floor(a);
  a = (a - deg) * 60;
  let min = Math.floor(a);
  let sec = Math.round((a - min) * 60);
  if (sec === 60) {
    sec = 0;
    min += 1;
  }
  if (min === 60) {
    min = 0;
    deg += 1;
  }
  const degStr = axis === "lon" ? String(deg).padStart(3, "0") : pad2(deg);
  return `${degStr}°${pad2(min)}'${pad2(sec)}"${hemi}`;
}

/** Degrees as a short graticule label: 37°30'N, 79°W. */
export function gridLabel(value: number, axis: "lat" | "lon"): string {
  const hemi = axis === "lat" ? (value >= 0 ? "N" : "S") : value >= 0 ? "E" : "W";
  const a = Math.abs(value);
  let deg = Math.floor(a + 1e-9);
  let min = Math.round((a - deg) * 60);
  if (min === 60) {
    min = 0;
    deg += 1;
  }
  return min ? `${deg}°${pad2(min)}'${hemi}` : `${deg}°${hemi}`;
}
