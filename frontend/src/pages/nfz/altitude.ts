// Altitude helpers shared by the map (plane colors, data tags) and the
// detail panel (altitude profile).

/** Altitude bands. Low planes are brightest: they are the ones that matter for airspace. */
export const ALTITUDE_BANDS = [
  { below: 5_000, color: "#e0fbff", label: "<5k" },
  { below: 18_000, color: "#67e8f9", label: "5–18k" },
  { below: 30_000, color: "#22d3ee", label: "18–30k" },
  { below: Infinity, color: "#0891b2", label: "30k+" },
] as const;

/** On the ground, or no recent position. */
export const GRAY = "#64748b";

/** The feed's altitude is text: feet, or "ground". Numbers pass through. */
export function altitudeFt(v: unknown): number | null {
  if (v == null) return null;
  if (typeof v === "number") return Number.isFinite(v) ? v : null;
  const s = String(v).trim();
  if (s.toLowerCase() === "ground") return 0;
  const n = parseFloat(s);
  return Number.isFinite(n) ? n : null;
}

export function altitudeColor(ft: number | null, stale = false): string {
  if (stale || ft == null || ft <= 0) return GRAY;
  return ALTITUDE_BANDS.find((b) => ft < b.below)!.color;
}

/** ATC data-tag style: hundreds of feet, so 35,000 ft reads "350"; "GND" on the ground. */
export function altitudeTag(ft: number | null): string {
  if (ft == null) return "---";
  if (ft <= 0) return "GND";
  return String(Math.round(ft / 100)).padStart(3, "0");
}

/**
 * A zone floor or ceiling the way a sectional chart prints it:
 * SFC, 500 AGL, 11,000, FL180.
 */
export function limitLabel(ft: unknown, datum: unknown): string {
  const d = String(datum ?? "").toUpperCase();
  const n = Number(ft);
  if (d === "SFC") return "SFC";
  if (ft == null || !Number.isFinite(n)) return d === "UNL" ? "UNL" : "—";
  if (d === "FL") return `FL${String(Math.round(n / 100)).padStart(3, "0")}`;
  const text = Math.round(n).toLocaleString("en-US");
  return d === "AGL" ? `${text} AGL` : text;
}
