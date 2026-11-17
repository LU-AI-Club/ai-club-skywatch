// NO-FLY-ZONE TEAM — this page is yours. Design it however you like; you are not
// bound by the shared look. What is here is a working starting point.
//
// Your detections carry zone columns (zone_id, zone_name, zone_type,
// duration_seconds) on each row from useNoFlyZoneDetections().
//
// The airspace polygons are NOT served by the API — fetch the static GeoJSON
// directly and overlay it (inside a <MapView>, add it with L.geoJSON). The
// fixtures live under air/detectors/no_fly_zone/fixtures/airspace/ in the repo;
// copy the two the live detector uses into public/airspace/ so the app can fetch
// them: klyh-local-faa.geojson (the 15 real zones) and klyh-demo.geojson (DEMO-1).
//   const zones = await fetch("/airspace/klyh-local-faa.geojson").then((r) => r.json());
// Each feature's properties.zone_id matches the zone_id column on a row. Not
// klyh-150nm.geojson: those are made-up test zones the live detector never loads.
import { useMemo } from "react";
import { useNoFlyZoneDetections } from "../api/hooks";
import { DetectionTable } from "../components/DetectionTable";
import { StatCard } from "../components/StatCard";
import { EmptyState } from "../components/EmptyState";

export function NoFlyZonePage() {
  const { data, loading, error, reload } = useNoFlyZoneDetections({ since_hours: 24 });
  const rows = data ?? [];
  const zones = useMemo(
    () => new Set(rows.map((d) => String(d.zone_id ?? "unknown"))).size,
    [rows],
  );

  return (
    <div className="page">
      <div className="page-head">
        <h1>No-fly zone</h1>
        <p className="owner">
          Owned by the No-fly-zone team — design this page however you like. This is a
          starting point.
        </p>
      </div>

      {error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}

      <div className="stat-grid">
        <StatCard label="Incursions (24h)" value={loading ? "…" : rows.length} />
        <StatCard label="Zones involved" value={loading ? "…" : zones} />
      </div>

      <div style={{ margin: "10px 0 16px" }}>
        <button className="btn ghost" onClick={reload} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <DetectionTable detections={rows} />
    </div>
  );
}
