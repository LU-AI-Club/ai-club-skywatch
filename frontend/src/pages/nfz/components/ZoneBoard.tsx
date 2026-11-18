// Every zone the live detector loads, with its incursion count. Zones with
// incursions get a hatched border and sort to the top. Click one to filter
// the feed, open its details and fly the map to it.
import type { ZoneInfo } from "../zones";
import { altitudeRange, scheduleLabel, zoneClass } from "../zones";
import { ZoneShape } from "./ZoneShape";

export function ZoneBoard({
  zones,
  counts,
  focusId,
  pinged,
  onPick,
}: {
  zones: ZoneInfo[];
  counts: Map<string, number>;
  focusId: string;
  pinged: Set<string>;
  onPick: (id: string) => void;
}) {
  if (!zones.length) {
    return (
      <div className="nfz-zones">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="nfz-zone nfz-zone--skel">
            <span className="nfz-skel nfz-skel--block" />
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="nfz-zones">
      {zones.map((z) => {
        const n = counts.get(z.id) ?? 0;
        const sched = scheduleLabel(z.activation);
        return (
          <button
            key={z.id}
            className={
              `nfz-zone nfz-zone--${zoneClass(z.type)}` +
              (n ? " is-active" : "") +
              (focusId === z.id ? " is-selected" : "") +
              (pinged.has(z.id) ? " is-pinged" : "")
            }
            aria-pressed={focusId === z.id}
            onClick={() => onPick(z.id)}
            title={`${z.name} · ${altitudeRange(z)}${z.schedule ? `\nTimes of use: ${z.schedule}` : ""}`}
          >
            <ZoneShape feature={z.feature} />
            <span className="nfz-zone-id">
              {z.id}
              {z.demo && <em className="nfz-demo">DEMO</em>}
            </span>
            <span className="nfz-zone-type">
              {z.type}
              {sched && <span className="nfz-zone-sched"> · {sched}</span>}
            </span>
            <span className="nfz-zone-count">{n}</span>
          </button>
        );
      })}
    </div>
  );
}
