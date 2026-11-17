// No-fly zone airspace on the map: the polygons the no-fly-zone detector checks
// aircraft against. The API doesn't serve them, so the app fetches the same
// static GeoJSON files the live detector loads (configs/detectors/no_fly_zone.yaml),
// copied into public/airspace/ from air/detectors/no_fly_zone/fixtures/airspace/.
// If the detector's zones change, re-copy those two files.
import { useEffect, useState } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "./mapContext";

const ZONE_FILES = ["/airspace/klyh-local-faa.geojson", "/airspace/klyh-demo.geojson"];

export const ZONE_CATEGORIES = [
  { key: "PROHIBITED", label: "Prohibited", color: "#ef4444" },
  { key: "RESTRICTED", label: "Restricted", color: "#f97316" },
  { key: "MOA", label: "Military ops (MOA)", color: "#eab308" },
  { key: "DEMO", label: "Demo zone", color: "#a1a1aa" },
  { key: "OTHER", label: "Other", color: "#94a3b8" },
] as const;

export type ZoneCategory = (typeof ZONE_CATEGORIES)[number]["key"];

interface ZoneProperties {
  zone_id?: string;
  name?: string;
  zone_type?: string;
  activation?: string;
  source?: string;
  source_asof?: string;
  times_of_use?: string;
  floor_ft?: number | null;
  floor_datum?: string | null;
  ceiling_ft?: number | null;
  ceiling_datum?: string | null;
  controlling_agency?: string;
}

export interface Zone {
  category: ZoneCategory;
  feature: GeoJSON.Feature<GeoJSON.Geometry, ZoneProperties>;
}

function categorize(p: ZoneProperties): ZoneCategory {
  if (p.source === "demo") return "DEMO";
  const t = (p.zone_type ?? "").toUpperCase();
  if (t === "PROHIBITED" || t === "RESTRICTED" || t === "MOA") return t;
  return "OTHER";
}

// Loads every zone file once. A file that fails to load is skipped, so one
// missing file doesn't hide the rest.
export function useNoFlyZones(): { zones: Zone[]; error: string | null } {
  const [zones, setZones] = useState<Zone[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled(
      ZONE_FILES.map(async (url) => {
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
        return (await res.json()) as GeoJSON.FeatureCollection<GeoJSON.Geometry, ZoneProperties>;
      }),
    ).then((results) => {
      if (controller.signal.aborted) return;
      const loaded: Zone[] = [];
      const failures: string[] = [];
      for (const r of results) {
        if (r.status === "fulfilled") {
          for (const f of r.value.features ?? []) {
            loaded.push({ category: categorize(f.properties ?? {}), feature: f });
          }
        } else {
          failures.push(String((r.reason as Error)?.message ?? r.reason));
        }
      }
      setZones(loaded);
      setError(failures.length ? `Couldn't load airspace (${failures.join("; ")})` : null);
    });
    return () => controller.abort();
  }, []);

  return { zones, error };
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function altitude(ft: number | null | undefined, datum: string | null | undefined): string {
  if (datum === "SFC" || ft === 0) return "Surface";
  if (typeof ft !== "number") return "—";
  if (datum === "FL") return `FL${Math.round(ft / 100)}`;
  return `${ft.toLocaleString()} ft${datum ? ` ${datum}` : ""}`;
}

function zonePopup(p: ZoneProperties, label: string): string {
  const rows: [string, string][] = [
    ["Type", label],
    ["Altitude", `${altitude(p.floor_ft, p.floor_datum)} – ${altitude(p.ceiling_ft, p.ceiling_datum)}`],
    ["Active", p.times_of_use ?? p.activation ?? "—"],
    ["Controlled by", p.controlling_agency ?? "—"],
  ];
  if (p.source_asof) rows.push(["FAA data as of", p.source_asof]);
  return `
    <div style="font-weight:600;margin-bottom:4px">${escapeHtml(p.zone_id ?? p.name)}</div>
    ${p.name && p.name !== p.zone_id ? `<div style="margin-bottom:4px">${escapeHtml(p.name)}</div>` : ""}
    <div style="color:#9a9aa5;line-height:1.5">
      ${rows.map(([k, v]) => `${k}: ${escapeHtml(v)}`).join("<br/>")}
    </div>`;
}

export function zoneCategory(key: ZoneCategory) {
  return ZONE_CATEGORIES.find((c) => c.key === key)!;
}

// Fit the map to a zone and open its details at the zone's center.
export function focusZone(map: L.Map, zone: Zone): void {
  const bounds = L.geoJSON(zone.feature).getBounds();
  if (!bounds.isValid()) return;
  map.flyToBounds(bounds, { padding: [40, 40], duration: 0.8, maxZoom: 12 });
  map.once("moveend", () => {
    L.popup()
      .setLatLng(bounds.getCenter())
      .setContent(zonePopup(zone.feature.properties ?? {}, zoneCategory(zone.category).label))
      .openOn(map);
  });
}

// Draws the zones whose category is switched on. Zones sit in their own pane
// below detections and aircraft, so they never cover a marker you want to click.
export function NoFlyZoneOverlay({
  zones,
  visible,
}: {
  zones: Zone[];
  visible: Record<ZoneCategory, boolean>;
}) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    if (!map.getPane("zones")) map.createPane("zones").style.zIndex = "350";
    const layer = L.layerGroup().addTo(map);
    for (const { category, feature } of zones) {
      if (!visible[category]) continue;
      const cat = zoneCategory(category);
      L.geoJSON(feature, {
        pane: "zones",
        style: {
          color: cat.color,
          weight: 1.5,
          opacity: 0.9,
          fillColor: cat.color,
          fillOpacity: category === "PROHIBITED" ? 0.18 : 0.08,
          dashArray: category === "DEMO" ? "6 5" : undefined,
        },
      })
        .bindPopup(zonePopup(feature.properties ?? {}, cat.label))
        .addTo(layer);
    }
    return () => {
      layer.remove();
    };
  }, [map, zones, visible]);
  return null;
}
