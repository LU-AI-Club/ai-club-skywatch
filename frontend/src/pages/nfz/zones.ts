// The airspace zones. They come from static GeoJSON files in public/airspace/
// (copied from air/detectors/no_fly_zone/fixtures/airspace/), not the API.
import { useEffect, useState } from "react";
import { limitLabel } from "./altitude";

export const ZONE_FILES = ["/airspace/klyh-local-faa.geojson", "/airspace/klyh-demo.geojson"];

// Sectional-chart colors: blue for prohibited/restricted, magenta for MOAs.
export const CHART_BLUE = "#4f8bff";
export const CHART_MAGENTA = "#e040fb";

export const TYPE_ORDER: Record<string, number> = { PROHIBITED: 0, RESTRICTED: 1, MOA: 2 };

export type ZoneFeature = {
  type: string;
  geometry: { type?: string; coordinates?: unknown } | null;
  properties?: Record<string, unknown>;
};
export type ZoneCollection = { type: string; features: ZoneFeature[] };

export type ZoneInfo = {
  id: string;
  name: string;
  type: string; // PROHIBITED / RESTRICTED / MOA
  demo: boolean;
  feature: ZoneFeature;
  activation: string; // ALWAYS / SCHEDULED / NOTAM, as published
  schedule: string; // the published times of use, as written
  floorFt: number | null;
  floorDatum: string;
  ceilingFt: number | null;
  ceilingDatum: string;
  agency: string;
  source: string;
};

/** "moa" or "restricted" (prohibited counts as restricted for coloring). */
export function zoneClass(type: unknown): "moa" | "restricted" {
  return String(type ?? "").toUpperCase() === "MOA" ? "moa" : "restricted";
}

export function zoneColor(type: unknown): string {
  return zoneClass(type) === "moa" ? CHART_MAGENTA : CHART_BLUE;
}

/** How a zone is switched on, as published. Whether it is active right now is the detector's call. */
export function scheduleLabel(activation: string): string {
  const a = activation.toUpperCase();
  if (a === "ALWAYS") return "ALWAYS";
  if (a === "SCHEDULED") return "SCHEDULED";
  if (a === "NOTAM") return "NOTAM";
  return "";
}

/** "SFC–FL180", "500 AGL–6,000" */
export function altitudeRange(z: Pick<ZoneInfo, "floorFt" | "floorDatum" | "ceilingFt" | "ceilingDatum">): string {
  return `${limitLabel(z.floorFt, z.floorDatum)}–${limitLabel(z.ceilingFt, z.ceilingDatum)}`;
}

function num(v: unknown): number | null {
  const n = Number(v);
  return v == null || v === "" || !Number.isFinite(n) ? null : n;
}

/** Turn the raw GeoJSON files into one ZoneInfo per zone_id. */
export function toZones(files: ZoneCollection[]): ZoneInfo[] {
  const seen = new Map<string, ZoneInfo>();
  for (const fc of files) {
    for (const f of fc.features ?? []) {
      const p = f.properties ?? {};
      const id = String(p.zone_id ?? "");
      if (!id || seen.has(id)) continue;
      seen.set(id, {
        id,
        name: String(p.name ?? id),
        type: String(p.zone_type ?? "").toUpperCase(),
        demo: id.startsWith("DEMO-"),
        feature: f,
        activation: String(p.activation ?? ""),
        schedule: String(p.times_of_use ?? ""),
        floorFt: num(p.floor_ft),
        floorDatum: String(p.floor_datum ?? ""),
        ceilingFt: num(p.ceiling_ft),
        ceilingDatum: String(p.ceiling_datum ?? ""),
        agency: p.controlling_agency == null ? "" : String(p.controlling_agency),
        source: [p.source, p.source_asof].filter((x) => x != null && x !== "").join(" · "),
      });
    }
  }
  return [...seen.values()];
}

// One fetch for the whole app session: the page and the map overlays share it.
let zoneFilesPromise: Promise<ZoneCollection[]> | null = null;
export function loadZoneFiles(): Promise<ZoneCollection[]> {
  if (!zoneFilesPromise) {
    zoneFilesPromise = Promise.all(
      ZONE_FILES.map((f) =>
        fetch(f).then((r) => {
          if (!r.ok) throw new Error(`${f}: ${r.status}`);
          return r.json() as Promise<ZoneCollection>;
        }),
      ),
    ).catch((e) => {
      zoneFilesPromise = null; // let a later call retry
      throw e;
    });
  }
  return zoneFilesPromise;
}

/** The raw zone files (for drawing). */
export function useZoneFiles(): ZoneCollection[] {
  const [files, setFiles] = useState<ZoneCollection[]>([]);
  useEffect(() => {
    let cancelled = false;
    loadZoneFiles()
      .then((f) => !cancelled && setFiles(f))
      .catch(() => !cancelled && setFiles([]));
    return () => {
      cancelled = true;
    };
  }, []);
  return files;
}

/** One ZoneInfo per zone. */
export function useZones(): ZoneInfo[] {
  const files = useZoneFiles();
  const [zones, setZones] = useState<ZoneInfo[]>([]);
  useEffect(() => setZones(toZones(files)), [files]);
  return zones;
}

/** A zone's outline as a small SVG path fitted into a w × h box (for thumbnails). */
export function shapePath(feature: ZoneFeature | null | undefined, w: number, h: number): string | null {
  const g = feature?.geometry;
  if (!g) return null;
  const rings: number[][][] =
    g.type === "Polygon"
      ? [(g.coordinates as number[][][])[0]]
      : g.type === "MultiPolygon"
        ? (g.coordinates as number[][][][]).map((poly) => poly[0])
        : [];
  const pts = rings.flat();
  if (!pts.length) return null;
  // Squash longitude by cos(latitude) so shapes keep their real proportions.
  const k = Math.cos(((pts.reduce((sum, q) => sum + q[1], 0) / pts.length) * Math.PI) / 180);
  const xs = pts.map((q) => q[0] * k);
  const ys = pts.map((q) => -q[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  const spanX = Math.max(...xs) - minX || 1e-9;
  const spanY = Math.max(...ys) - minY || 1e-9;
  const padding = 2;
  const scale = Math.min((w - 2 * padding) / spanX, (h - 2 * padding) / spanY);
  const ox = (w - spanX * scale) / 2;
  const oy = (h - spanY * scale) / 2;
  return rings
    .map(
      (r) =>
        r
          .map(
            (q, i) =>
              `${i ? "L" : "M"}${(ox + (q[0] * k - minX) * scale).toFixed(1)} ${(oy + (-q[1] - minY) * scale).toFixed(1)}`,
          )
          .join("") + "Z",
    )
    .join("");
}
