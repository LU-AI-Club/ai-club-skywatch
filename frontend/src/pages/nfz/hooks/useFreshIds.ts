import { useEffect, useRef, useState } from "react";
import type { Detection } from "../../../api/types";

/**
 * Detections that showed up since the page loaded (and started in the last
 * 10 minutes), so they can ripple on the map and flash in the feed for a few
 * seconds. Changing filters does not count as "new".
 */
export function useFreshIds(rows: Detection[] | null, holdMs = 8000): Set<string> {
  const seen = useRef<Set<string> | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const [fresh, setFresh] = useState<Set<string>>(() => new Set());
  useEffect(() => {
    if (!rows) return;
    if (!seen.current) {
      seen.current = new Set(rows.map((d) => d.detection_id));
      return;
    }
    const known = seen.current;
    const recent = Date.now() - 10 * 60_000;
    const added = rows
      .filter(
        (d) =>
          !known.has(d.detection_id) &&
          Date.parse(String(d.temporal_bounds_start ?? d.last_detected_at)) >= recent,
      )
      .map((d) => d.detection_id);
    rows.forEach((d) => known.add(d.detection_id));
    if (!added.length) return;
    setFresh(new Set(added));
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setFresh(new Set()), holdMs);
  }, [rows, holdMs]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return fresh;
}
