// When each incursion happened across the chosen time range. Each mark runs
// from when the aircraft entered the zone to when it left (or now, if open).
import type { Detection } from "../../../api/types";
import { zuluDay, zuluShort, zuluTime } from "../format";

export function Timeline({
  rows,
  hours,
  selectedId,
  onSelect,
}: {
  rows: Detection[];
  hours: number;
  selectedId: string | null;
  onSelect: (d: Detection) => void;
}) {
  const end = Date.now();
  const start = end - hours * 3_600_000;
  const pct = (t: number) => Math.min(100, Math.max(0, ((t - start) / (end - start)) * 100));
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => start + f * (end - start));
  const label = (t: number) => (hours > 24 ? zuluDay(t) : zuluShort(t));
  return (
    <div className="nfz-timeline">
      <div className="nfz-tl-track">
        {[0.25, 0.5, 0.75].map((f) => (
          <span key={f} className="nfz-tl-grid" style={{ left: `${f * 100}%` }} />
        ))}
        {rows.map((d) => {
          const t0 = Date.parse(String(d.temporal_bounds_start ?? d.last_detected_at));
          if (!Number.isFinite(t0)) return null;
          const t1 = d.temporal_bounds_end ? Date.parse(String(d.temporal_bounds_end)) : end;
          const left = pct(t0);
          const width = Math.max(0, pct(Number.isFinite(t1) ? t1 : t0) - left);
          return (
            <button
              key={d.detection_id}
              className={`nfz-tl-mark${d.detection_id === selectedId ? " is-selected" : ""}`}
              style={{
                left: `${left}%`,
                width: `max(4px, ${width}%)`,
                background: `var(--sev-${String(d.severity).toLowerCase()}, #64748b)`,
              }}
              title={`${d.entity_id} · ${String(d.zone_id ?? "")} · ${zuluTime(t0)}`}
              aria-label={`${d.severity} incursion by ${d.entity_id} into ${String(d.zone_id ?? "")} at ${zuluTime(t0)}`}
              onClick={() => onSelect(d)}
            />
          );
        })}
        {rows.length === 0 && <span className="nfz-tl-empty">no incursions in this window</span>}
      </div>
      <div className="nfz-tl-axis">
        {ticks.map((t, i) => (
          <span key={i}>{i === ticks.length - 1 ? "NOW" : label(t)}</span>
        ))}
      </div>
    </div>
  );
}
