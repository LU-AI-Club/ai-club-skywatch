// Aircraft that a detector flagged recently: they get lock-on brackets on the
// map, in the color of their worst severity.
import type { Detection } from "../../api/types";
import { severityColor, severityRank } from "./severity";

export type FlaggedAircraft = Map<string, { color: string; selected: boolean; severity: string; count: number }>;

/** Recent = still open, or seen in the last 30 minutes. */
export function isRecent(d: Detection, now = Date.now()): boolean {
  if (!d.temporal_bounds_end) return true;
  const t = Date.parse(String(d.last_detected_at));
  return Number.isFinite(t) && now - t < 30 * 60_000;
}

/** Keyed by entity_id ("icao24:a1b2c3"). The selected detection always counts. */
export function buildFlagged(detections: Detection[], selectedId?: string | null, now = Date.now()): FlaggedAircraft {
  const m: FlaggedAircraft = new Map();
  for (const d of detections) {
    const selected = d.detection_id === selectedId;
    if (!selected && !isRecent(d, now)) continue;
    const prev = m.get(d.entity_id);
    const worse = !prev || severityRank(d.severity) > severityRank(prev.severity);
    m.set(d.entity_id, {
      color: worse ? severityColor(d.severity) : prev!.color,
      severity: worse ? String(d.severity) : prev!.severity,
      selected: selected || !!prev?.selected,
      count: (prev?.count ?? 0) + 1,
    });
  }
  return m;
}
