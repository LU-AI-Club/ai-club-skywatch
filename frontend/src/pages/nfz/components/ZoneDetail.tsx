// One zone in full: its published limits and schedule, plus every incursion
// into it in the current time range and which aircraft keep coming back.
import type { Detection } from "../../../api/types";
import { SeverityBadge } from "../../../components/SeverityBadge";
import { altitudeRange, scheduleLabel, zoneClass, type ZoneInfo } from "../zones";
import { ago, duration, zuluTime } from "../format";
import { ZoneShape } from "./ZoneShape";

export function ZoneDetail({
  zone,
  detections,
  rangeLabel,
  onClose,
  onSelect,
}: {
  zone: ZoneInfo;
  detections: Detection[]; // this zone's incursions in the current time range
  rangeLabel: string;
  onClose: () => void;
  onSelect: (d: Detection) => void;
}) {
  const sorted = [...detections].sort(
    (a, b) => Date.parse(String(b.last_detected_at)) - Date.parse(String(a.last_detected_at)),
  );
  const byAircraft = new Map<string, Detection[]>();
  for (const d of sorted) byAircraft.set(d.entity_id, [...(byAircraft.get(d.entity_id) ?? []), d]);
  const repeat = [...byAircraft.entries()].sort((a, b) => b[1].length - a[1].length).slice(0, 6);
  const longest = sorted.reduce((m, d) => Math.max(m, Number(d.duration_seconds) || 0), 0);
  const sched = scheduleLabel(zone.activation);

  return (
    <section className={`nfz-zonedetail nfz-zonedetail--${zoneClass(zone.type)}`} aria-label={`Zone ${zone.id}`}>
      <div className="nfz-zd-head">
        <ZoneShape feature={zone.feature} w={88} h={64} className="nfz-zd-shape" />
        <div className="nfz-zd-title">
          <div className="nfz-zd-kicker">
            {zone.type}
            {sched && ` · ${sched}`}
            {zone.demo && " · DEMO (NOT REAL AIRSPACE)"}
          </div>
          <h2>{zone.name}</h2>
          <div className="nfz-zd-range">{altitudeRange(zone)}</div>
        </div>
        <button className="nfz-chip" onClick={onClose} title="Show all zones (Esc)">
          Show all zones ✕
        </button>
      </div>

      <dl className="nfz-zd-facts">
        <dt>Zone ID</dt>
        <dd>{zone.id}</dd>
        <dt>Times of use</dt>
        <dd>{zone.schedule || "—"}</dd>
        <dt>Controlling agency</dt>
        <dd>{zone.agency || "—"}</dd>
        <dt>Source</dt>
        <dd>{zone.source || "—"}</dd>
      </dl>

      <div className="nfz-zd-grid">
        <div>
          <div className="nfz-label">Incursions · last {rangeLabel}</div>
          <div className="nfz-zd-stats">
            <span>
              <b>{sorted.length}</b> incursions
            </span>
            <span>
              <b>{byAircraft.size}</b> aircraft
            </span>
            <span>
              <b>{sorted.length ? ago(sorted[0].last_detected_at) : "—"}</b> last
            </span>
            <span>
              <b>{sorted.length ? duration(longest) : "—"}</b> longest
            </span>
          </div>
          {sorted.length === 0 ? (
            <p className="nfz-zd-empty">No incursions into this zone in this time range.</p>
          ) : (
            <ul className="nfz-zd-list">
              {sorted.slice(0, 6).map((d) => (
                <li key={d.detection_id}>
                  <button onClick={() => onSelect(d)}>
                    <SeverityBadge severity={d.severity} />
                    <span>{d.entity_id}</span>
                    <span className="nfz-meta">{zuluTime(d.temporal_bounds_start)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <div className="nfz-label">Repeat aircraft</div>
          {repeat.length === 0 ? (
            <p className="nfz-zd-empty">—</p>
          ) : (
            <ul className="nfz-zd-list">
              {repeat.map(([entity, list]) => (
                <li key={entity}>
                  <button onClick={() => onSelect(list[0])} title="Open its latest incursion">
                    <span className="nfz-zd-count">{list.length}×</span>
                    <span>{entity}</span>
                    <span className="nfz-meta">last {ago(list[0].last_detected_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
