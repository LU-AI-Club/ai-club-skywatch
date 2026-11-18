import type { Detection } from "../../../api/types";
import { SeverityBadge } from "../../../components/SeverityBadge";
import { EmptyState } from "../../../components/EmptyState";
import { ago, duration, zuluShort, zuluTime } from "../format";
import { zoneClass } from "../zones";

export function IncursionTable({
  rows,
  loading,
  hasData,
  selectedId,
  fresh,
  emptyMessage,
  onSelect,
}: {
  rows: Detection[];
  loading: boolean;
  hasData: boolean;
  selectedId: string | null;
  fresh: Set<string>;
  emptyMessage: string;
  onSelect: (d: Detection) => void;
}) {
  if (!hasData && loading) {
    return (
      <table className="table nfz-table" aria-busy="true">
        <tbody>
          {Array.from({ length: 5 }, (_, i) => (
            <tr key={i}>
              <td colSpan={6}>
                <span className="nfz-skel nfz-skel--row" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    );
  }
  if (rows.length === 0) return <EmptyState message={emptyMessage} />;
  return (
    <table className="table nfz-table">
      <thead>
        <tr>
          <th>Severity</th>
          <th>Aircraft</th>
          <th>Zone</th>
          <th>Type</th>
          <th>Time inside</th>
          <th>Last detected</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((d) => {
          const selected = selectedId === d.detection_id;
          return (
            <tr
              key={d.detection_id}
              className={[fresh.has(d.detection_id) ? "nfz-row-new" : "", selected ? "is-selected" : ""].join(" ").trim() || undefined}
              onClick={() => onSelect(d)}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onSelect(d))}
              tabIndex={0}
              aria-selected={selected}
              data-detection={d.detection_id}
            >
              <td>
                <SeverityBadge severity={d.severity} />
              </td>
              <td>{d.entity_id}</td>
              <td title={String(d.zone_name ?? "")}>
                {String(d.zone_id ?? "—")}
                {String(d.zone_id ?? "").startsWith("DEMO-") && <em className="nfz-demo">DEMO</em>}
              </td>
              <td>
                <span className={`nfz-type nfz-type--${zoneClass(d.zone_type)}`}>{String(d.zone_type ?? "—")}</span>
              </td>
              <td>
                {duration(d.duration_seconds)}
                {!d.temporal_bounds_end && <span className="nfz-open">● open</span>}
              </td>
              <td title={zuluTime(d.last_detected_at)}>
                {zuluShort(d.last_detected_at)} · {ago(d.last_detected_at)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
