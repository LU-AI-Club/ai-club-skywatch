import { useEffect, useState } from "react";
import { fetchJSON } from "../../../api/client";
import type { Detection } from "../../../api/types";
import { parseTrack, windowTrack, type TrackPoint, type TrackResponse } from "../track";

/** The aircraft's recorded track around one incursion. */
export function useTrack(d: Detection | null): { points: TrackPoint[]; loading: boolean; error: string | null } {
  const [state, setState] = useState<{ points: TrackPoint[]; loading: boolean; error: string | null }>({
    points: [],
    loading: false,
    error: null,
  });
  const id = d?.detection_id;
  useEffect(() => {
    if (!d) return;
    const controller = new AbortController();
    const start = Date.parse(String(d.temporal_bounds_start ?? d.last_detected_at));
    const end = d.temporal_bounds_end ? Date.parse(String(d.temporal_bounds_end)) : Date.now();
    // Look back far enough to cover the incursion (the API allows up to 7 days).
    const hours = Number.isFinite(start) ? Math.min(168, Math.max(1, Math.ceil((Date.now() - start) / 3_600_000) + 1)) : 24;
    setState({ points: [], loading: true, error: null });
    fetchJSON<TrackResponse>("/observations/tracks", { entity_id: d.entity_id, lookback_hours: hours }, controller.signal)
      .then((res) => {
        const pts = parseTrack(res);
        setState({
          points: Number.isFinite(start) ? windowTrack(pts, start, Number.isFinite(end) ? end : start) : pts,
          loading: false,
          error: null,
        });
      })
      .catch((e) => {
        if ((e as Error).name === "AbortError") return;
        setState({ points: [], loading: false, error: (e as Error).message });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  return state;
}
