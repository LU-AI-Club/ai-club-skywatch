// frontend/src/components/SpoofingSummary.tsx
import { useMemo } from "react";
import type { Detection } from "../api/types";
import { StatCard } from "./StatCard";
import { SeverityBadge } from "./SeverityBadge";

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

interface Props {
  detections: Detection[];
  /** Time window the detections cover, in hours. If omitted, it's derived from the data. */
  windowHours?: number;
}

export default function SpoofingSummary({ detections, windowHours }: Props) {
  const stats = useMemo(() => {
    const total = detections.length;
    const aircraft = new Set(detections.map((d) => d.entity_id)).size;

    const bySeverity = new Map<string, number>();
    let confSum = 0;
    for (const d of detections) {
      const key = (d.severity ?? "unknown").toLowerCase();
      bySeverity.set(key, (bySeverity.get(key) ?? 0) + 1);
      confSum += d.confidence;
    }

    let hours = windowHours;
    if (hours === undefined && total > 1) {
      const times = detections.map((d) => new Date(d.last_detected_at).getTime());
      hours = (Math.max(...times) - Math.min(...times)) / 3_600_000;
    }
    // Under an hour of data makes the rate misleading, so show a dash instead.
    const perDay = hours && hours >= 1 ? (total / hours) * 24 : null;

    const severityRows = [...bySeverity.entries()].sort(
      ([a], [b]) =>
        (SEVERITY_ORDER.indexOf(a) + 1 || 99) - (SEVERITY_ORDER.indexOf(b) + 1 || 99)
    );

    return {
      total,
      aircraft,
      perDay,
      avgConfidence: total ? confSum / total : null,
      severityRows,
    };
  }, [detections, windowHours]);

  return (
    <div>
      <div className="stat-grid">
        <StatCard label="Detections" value={stats.total} />
        <StatCard
          label="Per day"
          value={stats.perDay === null ? "—" : Math.round(stats.perDay * 10) / 10}
        />
        <StatCard label="Aircraft affected" value={stats.aircraft} />
        <StatCard
          label="Avg confidence"
          value={stats.avgConfidence === null ? "—" : `${Math.round(stats.avgConfidence * 100)}%`}
        />
      </div>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", margin: "12px 0 16px" }}>
        {stats.severityRows.map(([sev, count]) => (
          <span key={sev} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <SeverityBadge severity={sev} />
            <strong>{count}</strong>
          </span>
        ))}
      </div>
    </div>
  );
}