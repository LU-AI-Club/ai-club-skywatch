// Data hooks each detector team calls from its own page. Each fetches on mount
// (and whenever its params change) and hands back { data, loading, error,
// reload }. The detection types are team-owned (see types.ts), so a team reads
// its own columns straight off the returned rows.
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJSON, type QueryParams } from "./client";
import type { Detection, DetectorRun } from "./types";

export interface FetchResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

function useFetch<T>(path: string, params?: QueryParams): FetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const key = JSON.stringify(params ?? {});

  const reload = useCallback(() => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    fetchJSON<T>(path, params, controller.signal)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        if ((e as Error).name !== "AbortError") setError((e as Error).message);
      })
      .finally(() => setLoading(false));
    // params captured via `key` so a new object with the same values is stable
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key]);

  useEffect(() => {
    reload();
    return () => abortRef.current?.abort();
  }, [reload]);

  return { data, loading, error, reload };
}

export function useSpoofingDetections(params?: QueryParams) {
  return useFetch<Detection[]>("/spoofing-detections", params);
}

export function useProximityDetections(params?: QueryParams) {
  return useFetch<Detection[]>("/proximity-detections", params);
}

export function useNoFlyZoneDetections(params?: QueryParams) {
  return useFetch<Detection[]>("/no-fly-zone-detections", params);
}

export function useDetectorRuns(params?: QueryParams) {
  return useFetch<DetectorRun[]>("/detector-runs", params);
}
