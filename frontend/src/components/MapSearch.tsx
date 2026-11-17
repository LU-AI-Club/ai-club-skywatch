// Search box for the map sidebar: finds live aircraft (callsign, ICAO hex,
// squawk) and no-fly zones (ID or name). Picking a result is handed back to the
// page, which moves the map.
import { useMemo, useState } from "react";
import type { AircraftFeature } from "../api/types";
import { zoneCategory, type Zone } from "../map/NoFlyZoneLayer";

const MAX_AIRCRAFT = 10;
const MAX_ZONES = 5;

type Result =
  | { kind: "aircraft"; key: string; aircraft: AircraftFeature; rank: number }
  | { kind: "zone"; key: string; zone: Zone; rank: number };

// 0 = exact, 1 = starts with, 2 = contains, null = no match.
function matchRank(value: string | null | undefined, q: string): number | null {
  if (!value) return null;
  const v = value.trim().toLowerCase();
  if (v === q) return 0;
  if (v.startsWith(q)) return 1;
  if (v.includes(q)) return 2;
  return null;
}

function bestRank(values: (string | null | undefined)[], q: string): number | null {
  let best: number | null = null;
  for (const v of values) {
    const r = matchRank(v, q);
    if (r !== null && (best === null || r < best)) best = r;
  }
  return best;
}

function altitudeLabel(alt: string | null): string {
  if (!alt) return "alt —";
  if (alt.toLowerCase() === "ground") return "on ground";
  const n = Number(alt);
  return Number.isFinite(n) ? `${n.toLocaleString()} ft` : alt;
}

export function MapSearch({
  aircraft,
  zones,
  onPickAircraft,
  onPickZone,
}: {
  aircraft: AircraftFeature[];
  zones: Zone[];
  onPickAircraft: (icao24: string) => void;
  onPickZone: (zone: Zone) => void;
}) {
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();

  const { aircraftResults, zoneResults, aircraftTotal, zoneTotal } = useMemo(() => {
    if (!q) return { aircraftResults: [], zoneResults: [], aircraftTotal: 0, zoneTotal: 0 };
    const a: Result[] = [];
    for (const f of aircraft) {
      const p = f.properties;
      const rank = bestRank([p.callsign, p.icao24, p.squawk], q);
      if (rank !== null) a.push({ kind: "aircraft", key: p.icao24, aircraft: f, rank });
    }
    const z: Result[] = [];
    for (const zone of zones) {
      const p = zone.feature.properties ?? {};
      const rank = bestRank([p.zone_id, p.name], q);
      if (rank !== null) z.push({ kind: "zone", key: p.zone_id ?? p.name ?? "", zone, rank });
    }
    const byRank = (x: Result, y: Result) => x.rank - y.rank || x.key.localeCompare(y.key);
    a.sort(byRank);
    z.sort(byRank);
    return {
      aircraftResults: a.slice(0, MAX_AIRCRAFT),
      zoneResults: z.slice(0, MAX_ZONES),
      aircraftTotal: a.length,
      zoneTotal: z.length,
    };
  }, [q, aircraft, zones]);

  const pick = (r: Result) => {
    if (r.kind === "aircraft") onPickAircraft(r.aircraft.properties.icao24);
    else onPickZone(r.zone);
  };

  const first = aircraftResults[0] ?? zoneResults[0];

  return (
    <div className="map-search">
      <div className="map-search-box">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor"
          strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && first) pick(first);
            if (e.key === "Escape") setQuery("");
          }}
          placeholder="Callsign, ICAO, squawk, zone…"
          aria-label="Search aircraft and no-fly zones"
          spellCheck={false}
          autoComplete="off"
        />
      </div>

      {q && (
        <div className="map-search-results" role="list" aria-live="polite">
          {aircraftTotal === 0 && zoneTotal === 0 && (
            <div className="map-search-empty">No matches for “{query.trim()}”</div>
          )}

          {aircraftTotal > 0 && (
            <div className="map-search-group">
              Aircraft · {aircraftTotal}
              {aircraftTotal > MAX_AIRCRAFT ? ` (showing ${MAX_AIRCRAFT})` : ""}
            </div>
          )}
          {aircraftResults.map((r) => {
            if (r.kind !== "aircraft") return null;
            const p = r.aircraft.properties;
            return (
              <button key={`a-${r.key}`} type="button" role="listitem"
                className="map-search-item" onClick={() => pick(r)}>
                <span className="map-search-title">{p.callsign?.trim() || "No callsign"}</span>
                <span className="map-search-meta">
                  {p.icao24.toUpperCase()} · {altitudeLabel(p.altitude)}
                  {p.squawk ? ` · sq ${p.squawk}` : ""}
                </span>
              </button>
            );
          })}

          {zoneTotal > 0 && (
            <div className="map-search-group">
              No-fly zones · {zoneTotal}
              {zoneTotal > MAX_ZONES ? ` (showing ${MAX_ZONES})` : ""}
            </div>
          )}
          {zoneResults.map((r) => {
            if (r.kind !== "zone") return null;
            const p = r.zone.feature.properties ?? {};
            const cat = zoneCategory(r.zone.category);
            return (
              <button key={`z-${r.key}`} type="button" role="listitem"
                className="map-search-item" onClick={() => pick(r)}>
                <span className="map-search-title">
                  <span className="swatch" style={{ background: cat.color }} />
                  {p.zone_id ?? p.name}
                </span>
                <span className="map-search-meta">{cat.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
