// The shared map page: live aircraft plus per-detector overlay modes you can
// toggle on and off. Each overlay reads its detector's endpoint and plots a
// point per detection. This page is platform-owned (shared design); the three
// detector dashboards are each team's own.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as L from "leaflet";
import { MapView, PLANE_PATH, type MapViewHandle } from "../map/MapView";
import { MapSearch } from "../components/MapSearch";
import {
  focusZone,
  NoFlyZoneOverlay,
  useNoFlyZones,
  type Zone,
  ZONE_CATEGORIES,
  type ZoneCategory,
} from "../map/NoFlyZoneLayer";
import { useLeafletMap } from "../map/mapContext";
import { useObservations } from "../api/observations";
import {
  useSpoofingDetections,
  useProximityDetections,
  useNoFlyZoneDetections,
} from "../api/hooks";
import { AIRCRAFT_TYPES, classifyAircraft, type AircraftType } from "../api/aircraftType";
import type { AircraftFeature, Detection } from "../api/types";

const OVERLAYS = [
  { key: "spoofing", label: "Spoofing", color: "#a855f7" },
  { key: "proximity", label: "Proximity", color: "#22d3ee" },
  { key: "no-fly-zone", label: "No-fly zone incursions", color: "#f59e0b" },
] as const;

type OverlayKey = (typeof OVERLAYS)[number]["key"];

const SIDEBAR_KEY = "skywatch.map.sidebarOpen";

// A detector overlay: renders markers for detections that carry coordinates,
// and cleans itself up. Rendered inside <MapView>, so it can grab the raw map.
function DetectionOverlay({
  detections,
  color,
}: {
  detections: Detection[];
  color: string;
}) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    for (const d of detections) {
      if (typeof d.latitude === "number" && typeof d.longitude === "number") {
        L.circleMarker([d.latitude, d.longitude], {
          radius: 9,
          color,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.25,
        })
          .bindPopup(
            `<b>${d.detector_id ?? "detection"}</b><br/>severity: ${d.severity}<br/>confidence: ${
              typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—"
            }`,
          )
          .addTo(layer);
      }
    }
    return () => {
      layer.remove();
    };
  }, [map, detections, color]);
  return null;
}

export function MapPage() {
  const [on, setOn] = useState<Record<OverlayKey, boolean>>({
    spoofing: true,
    proximity: true,
    "no-fly-zone": true,
  });
  const { aircraft, lastUpdated, error, simulated } = useObservations();

  // Filter sidebar open/closed, remembered per browser. Starts closed on
  // narrow screens, where it would cover most of the map.
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem(SIDEBAR_KEY);
      if (saved !== null) return saved === "1";
    } catch {
      // Storage blocked — fall through to the default.
    }
    return window.matchMedia("(min-width: 700px)").matches;
  });
  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, sidebarOpen ? "1" : "0");
    } catch {
      // Not remembered; it still works for this visit.
    }
  }, [sidebarOpen]);

  // No-fly zone airspace, filterable by zone type. Only types present in the
  // data get a checkbox.
  const { zones, error: zonesError } = useNoFlyZones();
  const [zonesOn, setZonesOn] = useState<Record<ZoneCategory, boolean>>({
    PROHIBITED: true,
    RESTRICTED: true,
    MOA: true,
    DEMO: true,
    OTHER: true,
  });
  const zoneCounts = useMemo(() => {
    const counts = Object.fromEntries(ZONE_CATEGORIES.map((c) => [c.key, 0])) as Record<
      ZoneCategory,
      number
    >;
    for (const z of zones) counts[z.category]++;
    return counts;
  }, [zones]);
  const zoneCats = ZONE_CATEGORIES.filter((c) => zoneCounts[c.key] > 0);

  // Search: jump the map to the picked aircraft or zone. On narrow screens the
  // sidebar covers the map, so close it to show the result.
  const mapViewRef = useRef<MapViewHandle>(null);
  const closeSidebarIfNarrow = () => {
    if (!window.matchMedia("(min-width: 700px)").matches) setSidebarOpen(false);
  };
  // Aircraft type filter (airliners / private / helicopters / other).
  const [typesOn, setTypesOn] = useState<Record<AircraftType, boolean>>({
    airliner: true,
    private: true,
    helicopter: true,
    other: true,
  });
  const typeCounts = useMemo(() => {
    const counts: Record<AircraftType, number> = { airliner: 0, private: 0, helicopter: 0, other: 0 };
    for (const f of aircraft) counts[classifyAircraft(f.properties)]++;
    return counts;
  }, [aircraft]);
  const allTypesOn = AIRCRAFT_TYPES.every((t) => typesOn[t.key]);
  const filterAircraft = useCallback(
    (f: AircraftFeature) => typesOn[classifyAircraft(f.properties)],
    [typesOn],
  );
  const visibleAircraft = useMemo(
    () => (allTypesOn ? aircraft : aircraft.filter(filterAircraft)),
    [aircraft, allTypesOn, filterAircraft],
  );

  const pickAircraft = useCallback((icao24: string) => {
    if (mapViewRef.current?.focusAircraft(icao24)) closeSidebarIfNarrow();
  }, []);
  const pickZone = useCallback((zone: Zone) => {
    const map = mapViewRef.current?.getMap();
    if (!map) return;
    // A zone whose type is filtered off would be invisible, so switch it on.
    setZonesOn((s) => (s[zone.category] ? s : { ...s, [zone.category]: true }));
    focusZone(map, zone);
    closeSidebarIfNarrow();
  }, []);

  // All three always fetch (cheap); overlays render only when toggled on.
  const spoofing = useSpoofingDetections({ since_hours: 24 });
  const proximity = useProximityDetections({ since_hours: 24 });
  const noFlyZone = useNoFlyZoneDetections({ since_hours: 24 });
  const data: Record<OverlayKey, Detection[] | null> = {
    spoofing: spoofing.data,
    proximity: proximity.data,
    "no-fly-zone": noFlyZone.data,
  };

  return (
    <div className={`map-page${sidebarOpen ? " sidebar-open" : ""}`}>
      <aside className="map-sidebar" aria-label="Map search and filters">
        <button
          type="button"
          className="map-sidebar-tab"
          onClick={() => setSidebarOpen((o) => !o)}
          aria-expanded={sidebarOpen}
          aria-controls="map-filters"
          title={sidebarOpen ? "Hide search & filters" : "Show search & filters"}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor"
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M9 6l6 6-6 6" />
          </svg>
          <span className="sr-only">{sidebarOpen ? "Hide search & filters" : "Show search & filters"}</span>
        </button>
        <div className="map-sidebar-head">Search &amp; filters</div>
        <div className="map-toggles" id="map-filters">
          <MapSearch
            aircraft={visibleAircraft}
            zones={zones}
            onPickAircraft={pickAircraft}
            onPickZone={pickZone}
          />

          <div className="map-toggles-heading map-toggles-section">Aircraft type</div>
          {AIRCRAFT_TYPES.map((t) => (
            <label key={t.key}>
              <input
                type="checkbox"
                checked={typesOn[t.key]}
                onChange={(e) => setTypesOn((s) => ({ ...s, [t.key]: e.target.checked }))}
              />
              <svg className="type-glyph" viewBox="0 0 23 24" width="15" height="15"
                style={{ fill: t.color }} aria-hidden="true">
                <path d={PLANE_PATH} />
              </svg>
              {t.label} ({typeCounts[t.key]})
            </label>
          ))}
          <div className="map-toggles-note">Faded planes = older positions</div>

          <div className="map-toggles-heading map-toggles-section">Detections (24h)</div>
          {OVERLAYS.map((o) => (
            <label key={o.key}>
              <input
                type="checkbox"
                checked={on[o.key]}
                onChange={(e) => setOn((s) => ({ ...s, [o.key]: e.target.checked }))}
              />
              <span className="swatch" style={{ background: o.color }} />
              {o.label}
              {data[o.key] ? ` (${data[o.key]!.length})` : ""}
            </label>
          ))}

          <div className="map-toggles-heading map-toggles-section">No-fly zones</div>
          <label>
            <input
              type="checkbox"
              checked={zoneCats.some((c) => zonesOn[c.key])}
              ref={(el) => {
                // Partly on → show the checkbox as indeterminate.
                if (el) {
                  const n = zoneCats.filter((c) => zonesOn[c.key]).length;
                  el.indeterminate = n > 0 && n < zoneCats.length;
                }
              }}
              onChange={(e) =>
                setZonesOn((s) => {
                  const next = { ...s };
                  for (const c of zoneCats) next[c.key] = e.target.checked;
                  return next;
                })
              }
            />
            All zones ({zones.length})
          </label>
          {zoneCats.map((c) => (
            <label key={c.key} className="map-toggles-sub">
              <input
                type="checkbox"
                checked={zonesOn[c.key]}
                onChange={(e) => setZonesOn((s) => ({ ...s, [c.key]: e.target.checked }))}
              />
              <span
                className="swatch"
                style={{
                  background: `color-mix(in srgb, ${c.color} 35%, transparent)`,
                  border: `1.5px ${c.key === "DEMO" ? "dashed" : "solid"} ${c.color}`,
                }}
              />
              {c.label} ({zoneCounts[c.key]})
            </label>
          ))}
          {zonesError && <div className="map-toggles-error">{zonesError}</div>}
        </div>
      </aside>

      <MapView ref={mapViewRef} filterAircraft={filterAircraft} style={{ height: "100%" }}>
        <NoFlyZoneOverlay zones={zones} visible={zonesOn} />
        {OVERLAYS.map((o) =>
          on[o.key] && data[o.key] ? (
            <DetectionOverlay key={o.key} detections={data[o.key]!} color={o.color} />
          ) : null,
        )}
      </MapView>

      <div className="map-status">
        {error
          ? `API unavailable — ${error}`
          : `${simulated ? "SIMULATED · " : ""}${
              allTypesOn ? aircraft.length : `${visibleAircraft.length} of ${aircraft.length}`
            } aircraft${
              lastUpdated ? ` · updated ${lastUpdated.toLocaleTimeString()}` : ""
            }`}
      </div>
    </div>
  );
}
