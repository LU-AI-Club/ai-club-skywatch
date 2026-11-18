// Is the live aircraft feed healthy? A dead feed and a quiet sky look the
// same on a map, so this says which one it is.
import { config } from "../../../config";
import { useObservations } from "../../../api/observations";
import { useNow } from "./useNow";

export type FeedHealth = {
  level: "ok" | "warn" | "down" | "loading";
  /** Seconds since the newest aircraft position in the feed. */
  newestAgeS: number | null;
  /** Seconds since the browser last got a response. */
  fetchedAgeS: number | null;
  message: string | null;
};

const STALE_DATA_S = 5 * 60;

function fmtAge(s: number): string {
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${Math.round(s / 3600)} h`;
}

export function useFeedHealth(): FeedHealth {
  const { aircraft, lastUpdated, error } = useObservations();
  const now = useNow(5000);
  const newest = aircraft.reduce((m, a) => Math.max(m, Date.parse(a.properties.observed_at) || 0), 0);
  const newestAgeS = newest ? Math.max(0, (now - newest) / 1000) : null;
  const fetchedAgeS = lastUpdated ? Math.max(0, (now - lastUpdated.getTime()) / 1000) : null;

  if (error) {
    return { level: "down", newestAgeS, fetchedAgeS, message: `Can't reach the API for live aircraft (${error}).` };
  }
  if (fetchedAgeS == null) return { level: "loading", newestAgeS, fetchedAgeS, message: null };
  if (fetchedAgeS > (3 * config.refreshIntervalMs) / 1000 + 5) {
    return {
      level: "warn",
      newestAgeS,
      fetchedAgeS,
      message: `Live aircraft haven't refreshed for ${fmtAge(fetchedAgeS)}.`,
    };
  }
  if (!aircraft.length) {
    return {
      level: "warn",
      newestAgeS,
      fetchedAgeS,
      message: "The feed has no aircraft from the last hour. The ADS-B poller may be stopped.",
    };
  }
  if (newestAgeS != null && newestAgeS > STALE_DATA_S) {
    return {
      level: "warn",
      newestAgeS,
      fetchedAgeS,
      message: `Newest aircraft position is ${fmtAge(newestAgeS)} old. The ADS-B poller may be stopped.`,
    };
  }
  return { level: "ok", newestAgeS, fetchedAgeS, message: null };
}

export { fmtAge };
