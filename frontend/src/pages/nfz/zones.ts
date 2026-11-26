// No-fly-zone page helpers: the airspace GeoJSON (served statically from
// public/airspace/), zone-type colors, and small readers over a detection row.
import { useEffect, useState } from "react";
import type { Detection } from "../../api/types";

// The two files the live detector loads (see air/detectors/no_fly_zone/live.py).
// klyh-150nm.geojson is deliberately absent: made-up test zones.
const AIRSPACE_FILES = ["/airspace/klyh-local-faa.geojson", "/airspace/klyh-demo.geojson"];

export type ZoneType = "PROHIBITED" | "RESTRICTED" | "TFR" | "WARNING" | "ALERT" | "MOA";

export interface ZoneProperties {
  zone_id: string;
  name?: string;
  zone_type: ZoneType | string;
  activation?: string; // ALWAYS | SCHEDULED | NOTAM
  source?: string;
  source_asof?: string;
  times_of_use?: string;
  floor_ft?: number;
  floor_datum?: string;
  ceiling_ft?: number;
  ceiling_datum?: string;
  controlling_agency?: string;
}

export interface ZoneFeature {
  type: "Feature";
  geometry: GeoJSON.Geometry;
  properties: ZoneProperties;
}

// Ordered most to least restrictive; drives legend order and filter chips.
export const ZONE_TYPES: { type: ZoneType; label: string; color: string }[] = [
  { type: "PROHIBITED", label: "Prohibited", color: "#ef4444" },
  { type: "RESTRICTED", label: "Restricted", color: "#f97316" },
  { type: "TFR", label: "TFR", color: "#ec4899" },
  { type: "WARNING", label: "Warning", color: "#eab308" },
  { type: "ALERT", label: "Alert", color: "#a3e635" },
  { type: "MOA", label: "MOA", color: "#818cf8" },
];

export function zoneColor(type: string | null | undefined): string {
  return ZONE_TYPES.find((z) => z.type === type)?.color ?? "#64748b";
}

export function useAirspace() {
  const [zones, setZones] = useState<ZoneFeature[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    Promise.all(
      AIRSPACE_FILES.map((url) =>
        fetch(url).then((r) => {
          if (!r.ok) throw new Error(`${url} returned ${r.status}`);
          return r.json() as Promise<{ features: ZoneFeature[] }>;
        }),
      ),
    )
      .then((collections) => {
        if (!cancelled) setZones(collections.flatMap((c) => c.features ?? []));
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  return { zones, error };
}

// ---- reading a detection row ------------------------------------------------

interface NfzMetadata {
  explanation_facts?: string[];
  limitations?: string[];
  anomaly_score?: number;
  extras?: {
    altitude_ft?: number;
    penetration_nm?: number;
    dwell_sec?: number;
    episode_status?: string;
  };
}

export function meta(d: Detection): NfzMetadata {
  const m = d.metadata;
  return m && typeof m === "object" ? (m as NfzMetadata) : {};
}

export const zoneIdOf = (d: Detection) => String(d.zone_id ?? "unknown");
export const zoneTypeOf = (d: Detection) => String(d.zone_type ?? "");
export const zoneNameOf = (d: Detection) => String(d.zone_name ?? d.zone_id ?? "Unknown zone");

// An episode with no end time is still in progress.
export const isOngoing = (d: Detection) => d.temporal_bounds_end == null;

export function durationSeconds(d: Detection, now = Date.now()): number | null {
  if (typeof d.duration_seconds === "number") return d.duration_seconds;
  if (isOngoing(d)) {
    const start = Date.parse(d.temporal_bounds_start);
    return Number.isNaN(start) ? null : Math.max(0, (now - start) / 1000);
  }
  return null;
}

// ---- formatting --------------------------------------------------------------

export function fmtDuration(sec: number | null): string {
  if (sec == null || !Number.isFinite(sec)) return "—";
  if (sec < 60) return `${Math.round(sec)}s`;
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}m ${Math.round(sec % 60)}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function fmtAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const s = Math.max(0, (now - t) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
}

export function fmtAltBand(p: ZoneProperties): string {
  const one = (ft?: number, datum?: string) => {
    if (datum === "SFC" || ft === 0) return "SFC";
    if (ft == null) return "?";
    if (datum === "FL") return `FL${Math.round(ft / 100)}`;
    return `${ft.toLocaleString()} ft${datum ? ` ${datum}` : ""}`;
  };
  return `${one(p.floor_ft, p.floor_datum)} – ${one(p.ceiling_ft, p.ceiling_datum)}`;
}

export function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
