// PROXIMITY TEAM — this page is yours. Design it however you like; you are not
// bound by the shared look. What is here is a working starting point.
//
// Your detections carry pair-specific columns (member_entity_ids,
// predicted_horizontal_nm, predicted_vertical_ft, t_cpa_seconds). They come
// through on each row from useProximityDetections() — read them straight off
// the row, e.g. d.predicted_horizontal_nm.
import { useMemo } from "react";
import { useProximityDetections } from "../api/hooks";
import { DetectionTable } from "../components/DetectionTable";
import { StatCard } from "../components/StatCard";
import { EmptyState } from "../components/EmptyState";
import DetectorHealth from "../components/DetectorHealth";

export function ProximityPage() {
  const { data, loading, error, reload } = useProximityDetections({ since_hours: 24 });
  const rows = data ?? [];
  const highOrWorse = useMemo(
    () => rows.filter((d) => ["high", "critical"].includes(String(d.severity).toLowerCase())).length,
    [rows],
  );

  return (
    <div className="page">
      <div className="page-head">
        <h1>Proximity</h1>
        <p className="owner">
          Owned by the Proximity team — design this page however you like. This is a
          starting point.
        </p>
      </div>
	
	<DetectorHealth />
      
	{error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}

      <div className="stat-grid">
        <StatCard label="Detections (24h)" value={loading ? "…" : rows.length} />
        <StatCard label="High / critical" value={loading ? "…" : highOrWorse} />
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
