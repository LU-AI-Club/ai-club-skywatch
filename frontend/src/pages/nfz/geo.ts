// Small flat-earth helpers. Fine over the tens of miles this map covers.

export type LatLon = { lat: number; lon: number };

/** Distance in nautical miles. */
export function nmBetween(a: LatLon, b: LatLon): number {
  const dLat = (b.lat - a.lat) * 60;
  const dLon = (b.lon - a.lon) * 60 * Math.cos((a.lat * Math.PI) / 180);
  return Math.hypot(dLat, dLon);
}

/** The point `nm` nautical miles from `from` along a true course in degrees. */
export function project(from: LatLon, courseDeg: number, nm: number): LatLon {
  const rad = (courseDeg * Math.PI) / 180;
  return {
    lat: from.lat + (nm * Math.cos(rad)) / 60,
    lon: from.lon + (nm * Math.sin(rad)) / (60 * Math.cos((from.lat * Math.PI) / 180)),
  };
}

/** Lynchburg Regional Airport (KLYH), the center of our range rings. */
export const KLYH: LatLon = { lat: 37.3267, lon: -79.2004 };
