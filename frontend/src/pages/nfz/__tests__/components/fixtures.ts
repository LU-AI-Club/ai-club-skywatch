// Small builders for component tests.
import type { AircraftFeature, Detection } from "../../../../api/types";

export const NOW = Date.now();

export function det(id: string, minsAgo: number, extra: Partial<Detection> = {}): Detection {
  const start = NOW - minsAgo * 60_000;
  return {
    detection_id: id,
    detector_id: "skywatch.no_fly_zone",
    detector_version: "1",
    detection_type: "nfz",
    severity: "high",
    confidence: 0.9,
    entity_id: "icao24:a1b2c3",
    latitude: 37.3,
    longitude: -79.2,
    temporal_bounds_start: new Date(start).toISOString(),
    temporal_bounds_end: new Date(start + 60_000).toISOString(),
    last_detected_at: new Date(start + 60_000).toISOString(),
    zone_id: "P-56",
    zone_name: "P-56",
    zone_type: "PROHIBITED",
    duration_seconds: 60,
    ...extra,
  };
}

export function plane(id: string, extra: Partial<AircraftFeature["properties"]> = {}): AircraftFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [-79.0, 37.5] },
    properties: {
      icao24: id,
      callsign: "DAL1729",
      altitude: "9000",
      squawk: "1200",
      category: "A3",
      sog: 230,
      cog: 300,
      heading: 300,
      latitude: 37.5,
      longitude: -79.0,
      observed_at: new Date(NOW - 3000).toISOString(),
      position_age_hours: 0.001,
      source_id: "test",
      ...extra,
    },
  };
}
