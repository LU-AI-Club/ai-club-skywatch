// The moment the map is showing: null means live; a time (ms) means sky
// replay. Overlays read it so incursions appear only once they've happened.
import { createContext, useContext } from "react";
import type { Detection } from "../../../api/types";

export const ReplayContext = createContext<number | null>(null);

export function useReplayAt(): number | null {
  return useContext(ReplayContext);
}

/** Detections as of a replay moment (all of them when live). */
export function asOf(detections: Detection[], at: number | null): Detection[] {
  if (at == null) return detections;
  return detections.filter((d) => {
    const t = Date.parse(String(d.temporal_bounds_start ?? d.last_detected_at));
    return Number.isFinite(t) && t <= at;
  });
}
