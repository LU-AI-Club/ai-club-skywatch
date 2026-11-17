// A plain starter table over the common detection columns. Teams are expected to
// replace or extend this — it exists so a page shows something on day one.
import type { Detection } from "../api/types";
import { SeverityBadge } from "./SeverityBadge";
import { EmptyState } from "./EmptyState";

function shortTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

export function DetectionTable({ detections }: { detections: Detection[] }) {
  if (!detections.length) {
    return <EmptyState message="No detections for the current filters." />;
  }
  return (
    <table className="table">
      <thead>
        <tr>
          <th>Severity</th>
          <th>Aircraft</th>
          <th>Type</th>
          <th>Confidence</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        {detections.map((d) => (
          <tr key={d.detection_id}>
            <td>
              <SeverityBadge severity={d.severity} />
            </td>
            <td>{d.entity_id}</td>
            <td>{d.detection_type}</td>
            <td>{typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—"}</td>
            <td>{shortTime(d.last_detected_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
