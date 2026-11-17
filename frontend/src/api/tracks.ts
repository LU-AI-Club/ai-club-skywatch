// One aircraft's path, for drawing its trail on the map. Comes from the API's
// /observations/tracks endpoint, or from the simulator when ?simulate is on.
import { fetchJSON } from "./client";
import { simulatedTrack } from "./simulator";

export interface TrackPoint {
  lat: number;
  lon: number;
  altitude: string | null;
  observedAt: string; // ISO
}

// How far back to look for a path. The API caps this at 168 h.
const LOOKBACK_HOURS = 12;
// A silence this long means the aircraft landed (or left coverage) and later
// came back as a new flight; only the latest flight is drawn.
const NEW_FLIGHT_GAP_MS = 20 * 60 * 1000;

interface ApiTrackPoint {
  observed_at: string;
  latitude: number;
  longitude: number;
  altitude: string | null;
}

interface ApiTrackResponse {
  features: { properties: { points: ApiTrackPoint[] } }[];
}

// Keep only the points after the last long gap: the current flight.
export function currentFlight(points: TrackPoint[]): TrackPoint[] {
  for (let i = points.length - 1; i > 0; i--) {
    const gap = Date.parse(points[i].observedAt) - Date.parse(points[i - 1].observedAt);
    if (gap > NEW_FLIGHT_GAP_MS) return points.slice(i);
  }
  return points;
}

export async function fetchTrack(icao24: string, signal?: AbortSignal): Promise<TrackPoint[]> {
  const simulated = simulatedTrack(icao24);
  if (simulated) return simulated;

  const res = await fetchJSON<ApiTrackResponse>(
    "/observations/tracks",
    { entity_id: icao24, lookback_hours: LOOKBACK_HOURS, limit: 10000 },
    signal,
  );
  const points = (res.features?.[0]?.properties?.points ?? [])
    .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
    .map((p) => ({
      lat: p.latitude,
      lon: p.longitude,
      altitude: p.altitude,
      observedAt: p.observed_at,
    }));
  return currentFlight(points);
}
