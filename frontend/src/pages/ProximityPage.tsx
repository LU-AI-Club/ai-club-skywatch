import { useState } from "react";
import { useProximityDetections } from "../api/hooks";
import type { Detection } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { SeverityBadge } from "../components/SeverityBadge";
import { StatCard } from "../components/StatCard";

const ranges = [
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 168 },
  { label: "14 days", hours: 336 },
] as const;
type Range = (typeof ranges)[number]["hours"];

function numeric(row: Detection, key: string): number | null {
  const value = row[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatted(value: number | null, digits: number, unit: string): string {
  return value === null ? "—" : `${value.toFixed(digits)} ${unit}`;
}

function smallest(rows: Detection[], key: string): number | null {
  const values = rows.map((row) => numeric(row, key)).filter((value): value is number => value !== null);
  return values.length ? Math.min(...values) : null;
}

function pair(row: Detection): string[] {
  return Array.isArray(row.member_entity_ids)
    ? row.member_entity_ids.filter((id): id is string => typeof id === "string")
    : [];
}

function detectedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function ProximityPage() {
  const [hours, setHours] = useState<Range>(336);
  const { data, loading, error, reload } = useProximityDetections({ since_hours: hours });
  const rows = loading || error ? [] : (data ?? []);
  const mediumOrHigher = rows.filter((row) =>
    ["medium", "high", "critical"].includes(row.severity.toLowerCase()),
  ).length;
  const sortedRows = [...rows].sort((a, b) =>
    Date.parse(b.last_detected_at) - Date.parse(a.last_detected_at),
  );

  return (
    <div className="page proximity-page">
      <style>{`
        .proximity-page .page-head { display: flex; align-items: end; justify-content: space-between; flex-wrap: wrap; gap: 18px; margin-bottom: 24px; padding-bottom: 22px; border-bottom: 1px solid var(--border); }
        .proximity-page .page-head h1 { font-size: clamp(28px, 4vw, 38px); letter-spacing: -.035em; }
        .proximity-page .page-head .owner { margin-bottom: 0; }
        .proximity-page .controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
        .proximity-page select { background: var(--raised); color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; font: inherit; }
        .proximity-page select:focus-visible, .proximity-page button:focus-visible { outline: 2px solid #78c8f8; outline-offset: 2px; }
        .proximity-page .stat-grid { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin: 0; }
        .proximity-page .stat { min-height: 108px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); padding: 18px; }
        .proximity-page .stat:nth-child(2) { border-top: 2px solid var(--accent); }
        .proximity-page .stat .label { line-height: 1.3; }
        .proximity-page .stat .value { font-variant-numeric: tabular-nums; font-size: clamp(20px, 2vw, 27px); letter-spacing: -.025em; }
        .proximity-page .section-head { margin-top: 30px; display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
        .proximity-page .section-head h2 { margin: 0; font-size: 20px; }
        .proximity-page .section-head span { color: var(--muted); font-size: 13px; }
        .proximity-page .table-wrap { overflow-x: auto; margin-top: 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
        .proximity-page .pair-table { width: 100%; min-width: 680px; border-collapse: collapse; }
        .proximity-page .pair-table th, .proximity-page .pair-table td { padding: 15px 16px; border-bottom: 1px solid var(--border); text-align: left; }
        .proximity-page .pair-table th { color: var(--muted); font-size: .75rem; letter-spacing: .06em; text-transform: uppercase; }
        .proximity-page .pair-table tbody tr:last-child td { border-bottom: 0; }
        .proximity-page .pair-table tbody tr:hover { background: var(--raised); }
        .proximity-page .pair-table td:not(:first-child) { font-variant-numeric: tabular-nums; white-space: nowrap; }
        .proximity-page .aircraft-pair { font-weight: 650; }
        .proximity-page .pair-separator { color: var(--muted); margin: 0 8px; }
        .proximity-page .context-note { margin-top: 16px; color: var(--muted); font-size: 12px; }
        @media (max-width: 760px) { .proximity-page .stat-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
        @media (max-width: 440px) { .proximity-page .stat-grid { grid-template-columns: 1fr; } .proximity-page .controls { width: 100%; } }
      `}</style>
      <div className="page-head">
        <div>
          <h1>Aircraft proximity</h1>
          <p className="owner">See how close two aircraft were predicted to pass when each alert was recorded.</p>
        </div>
        <div className="controls">
          <label htmlFor="proximity-range">Time range</label>
          <select id="proximity-range" value={hours} onChange={(event) => setHours(Number(event.target.value) as Range)}>
            {ranges.map((range) => <option key={range.hours} value={range.hours}>{range.label}</option>)}
          </select>
          <button className="btn ghost" onClick={reload} disabled={loading}>{loading ? "Refreshing…" : "Refresh"}</button>
        </div>
      </div>

      {error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}
      <div className="stat-grid">
        <StatCard label="Detected pairs" value={loading ? "…" : error ? "—" : rows.length} />
        <StatCard label="Tightest horizontal approach" value={loading ? "…" : error ? "—" : formatted(smallest(rows, "predicted_horizontal_nm"), 2, "nm")} />
        <StatCard label="Smallest vertical gap" value={loading ? "…" : error ? "—" : formatted(smallest(rows, "predicted_vertical_ft"), 0, "ft")} />
        <StatCard label="Medium or higher" value={loading ? "…" : error ? "—" : mediumOrHigher} />
      </div>

      {loading ? <EmptyState message="Loading proximity detections…" /> :
        error ? null : rows.length === 0 ? <EmptyState message="No proximity detections in this time range." /> : (
        <>
        <div className="section-head"><h2>Pair alerts</h2><span>Most recently seen first · {rows.length} total</span></div>
        <div className="table-wrap">
          <table className="pair-table">
            <thead><tr>
              <th scope="col">Aircraft pair</th>
              <th scope="col">Horizontal at CPA</th>
              <th scope="col">Vertical at CPA</th>
              <th scope="col">Time to CPA</th>
              <th scope="col">Severity</th>
              <th scope="col">Last seen</th>
            </tr></thead>
            <tbody>{sortedRows.map((row) => (
              <tr key={row.detection_id}>
                <td className="aircraft-pair">{pair(row).length ? pair(row).map((id, index) => (
                  <span key={`${id}-${index}`}>{index > 0 && <span className="pair-separator" aria-hidden="true">↔</span>}{id.replace(/^aircraft:/, "").toUpperCase()}</span>
                )) : "—"}</td>
                <td>{formatted(numeric(row, "predicted_horizontal_nm"), 2, "nm")}</td>
                <td>{formatted(numeric(row, "predicted_vertical_ft"), 0, "ft")}</td>
                <td>{formatted(numeric(row, "t_cpa_seconds"), 0, "s")}</td>
                <td><SeverityBadge severity={row.severity} /></td>
                <td>{detectedAt(row.last_detected_at)}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className="context-note">Predictions assume constant speed and heading. Aircraft clearances and intent are not available from ADS-B.</p>
        </>
      )}
    </div>
  );
}
