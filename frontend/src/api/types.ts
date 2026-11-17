// Shapes returned by the SkyWatch API (see api/main.py and docs/FRONTEND_PLAN.md).

export interface AircraftProperties {
  icao24: string;
  callsign: string | null;
  altitude: string | null; // text: may be a number-as-string or "ground"
  squawk: string | null;
  category: string | null;
  sog: number | null; // knots
  cog: number | null; // degrees
  heading: number | null; // degrees
  latitude: number;
  longitude: number;
  observed_at: string; // ISO
  position_age_hours: number;
  source_id: string;
}

export interface AircraftFeature {
  type: "Feature";
  id: string; // ICAO hex
  geometry: { type: "Point"; coordinates: [number, number] }; // [lon, lat]
  properties: AircraftProperties;
}

export interface FeatureCollection<F> {
  type: "FeatureCollection";
  features: F[];
}

// Detections are TEAM-OWNED: the API returns each row as stored, so the shape is
// whatever a team's table has. The common columns every detector shares are
// declared for convenience; anything else is reachable through the index
// signature, so a team can read its own columns without changing this type.
export interface Detection {
  detection_id: string;
  detector_id: string;
  detector_version: string;
  detection_type: string;
  severity: string;
  confidence: number;
  entity_id: string;
  latitude: number | null;
  longitude: number | null;
  temporal_bounds_start: string;
  temporal_bounds_end: string | null;
  last_detected_at: string;
  [column: string]: unknown;
}

export interface DetectorRun {
  detection_run_id: string;
  detector_id: string;
  detector_version: string;
  window_start: string | null;
  window_end: string | null;
  started_at: string;
  completed_at: string | null;
  status: string; // RUNNING | SUCCESS | FAILED
  counts: Record<string, unknown>;
  error: string | null;
}
