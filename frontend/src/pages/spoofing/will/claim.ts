// Pulling the claim-versus-reality pair out of a finding.
//
// This is the whole idea the page is built on. Every physics rule we have is
// one comparison: the aircraft said a number, its positions imply a different
// number, and the gap between them is the finding. The detector already did
// that arithmetic and left both sides in the evidence, so the page only has to
// find them.
//
// Identity rules have no such pair — "this address carried two callsigns" is
// not a measurement — so they return null and are rendered differently rather
// than being forced into a shape that does not fit.
import type { Detection } from "../../../api/types";

export interface Claim {
  /** What the aircraft said about itself. */
  claimed: number;
  /** What its positions actually imply. */
  actual: number;
  unit: string;
  /** How the two differ, as a multiple. 2 means "twice what it claimed". */
  ratio: number;
  /** Seconds between the two reports this was computed from. */
  dtSeconds: number | null;
  /** Metres covered between them. */
  distanceM: number | null;
}

function evidenceMeta(d: Detection): Record<string, unknown> {
  const ev = d.evidence;
  if (!Array.isArray(ev) || ev.length === 0) return {};
  const first = ev[0];
  if (!first || typeof first !== "object") return {};
  const m = (first as Record<string, unknown>).metadata;
  return m && typeof m === "object" ? (m as Record<string, unknown>) : {};
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

export function claimOf(d: Detection): Claim | null {
  // Only the speed rule. Every finding carries the speed pair in its evidence,
  // but for a turn-rate or climb-rate finding that pair is not what fired --
  // the aircraft's speed agreed perfectly while its *turn* did not. Showing
  // "said 505, did 505, 1.0x what it claimed" next to a HIGH severity card
  // reads as "this aircraft was consistent", which is the opposite of true.
  //
  // So the said/did comparison is shown where it is the finding, and every
  // other rule shows its own measured value against its own limit instead.
  if (gateOf(d) !== "speed_delta_v1") return null;

  const m = evidenceMeta(d);
  const claimed = num(m.reported_speed_kt);
  const actual = num(m.implied_speed_kt);
  if (claimed === null || actual === null) return null;

  // A claimed speed of zero is a real value (a parked aircraft), but it makes
  // a ratio meaningless, so the card falls back to showing the raw pair.
  const ratio = claimed > 0 ? actual / claimed : Number.NaN;

  return {
    claimed,
    actual,
    unit: "kt",
    ratio,
    dtSeconds: num(m.dt_s),
    distanceM: num(m.dist_m),
  };
}

export function metaOf(d: Detection): Record<string, unknown> {
  const m = d.metadata;
  return m && typeof m === "object" ? (m as Record<string, unknown>) : {};
}

export function gateOf(d: Detection): string {
  const g = metaOf(d).gate;
  return typeof g === "string" ? g : (d.detection_type ?? "unknown");
}

export function factsOf(d: Detection): string[] {
  const f = metaOf(d).explanation_facts;
  return Array.isArray(f) ? f.filter((x): x is string => typeof x === "string") : [];
}

export function limitsOf(d: Detection): string[] {
  const l = metaOf(d).limitations;
  return Array.isArray(l) ? l.filter((x): x is string => typeof x === "string") : [];
}

/** The measured value and the limit it broke, in the detector's own units. */
export function measurementOf(d: Detection): {
  measured: number;
  threshold: number;
  unit: string;
  overPercent: number;
} | null {
  const e = metaOf(d).event;
  if (!e || typeof e !== "object") return null;
  const ev = e as Record<string, unknown>;
  const measured = num(ev.measured);
  const threshold = num(ev.threshold);
  if (measured === null || threshold === null || threshold === 0) return null;
  return {
    measured,
    threshold,
    unit: typeof ev.unit === "string" ? ev.unit : "",
    overPercent: ((measured - threshold) / Math.abs(threshold)) * 100,
  };
}
