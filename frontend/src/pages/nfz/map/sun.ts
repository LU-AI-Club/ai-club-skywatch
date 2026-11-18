// Where it is night right now: the day/night line (solar terminator). The
// standard low-precision solar position formulas, good to a fraction of a
// degree, which is plenty for shading a map.
const rad = Math.PI / 180;

export function julianDay(date: Date): number {
  return date.getTime() / 86_400_000 + 2440587.5;
}

/** Sun's right ascension and declination (degrees) and Greenwich sidereal time (hours). */
export function sunPosition(date: Date): { ra: number; dec: number; gmst: number } {
  const jd = julianDay(date);
  const n = jd - 2451545.0;
  const L = (280.46 + 0.9856474 * n) % 360;
  const g = ((357.528 + 0.9856003 * n) % 360) * rad;
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * rad;
  const eps = (23.439 - 0.0000004 * n) * rad;
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda)) / rad;
  const dec = Math.asin(Math.sin(eps) * Math.sin(lambda)) / rad;
  const gmst = (((18.697374558 + 24.06570982441908 * n) % 24) + 24) % 24;
  return { ra: (ra + 360) % 360, dec, gmst };
}

/** The point on Earth where the sun is straight overhead. */
export function subsolarPoint(date: Date): { lat: number; lon: number } {
  const { ra, dec, gmst } = sunPosition(date);
  let lon = ra - gmst * 15;
  lon = ((((lon + 180) % 360) + 360) % 360) - 180;
  return { lat: dec, lon };
}

/** Sun elevation in degrees at a place and time (positive = daytime). */
export function sunElevation(lat: number, lon: number, date: Date): number {
  const s = subsolarPoint(date);
  const cosZ =
    Math.sin(lat * rad) * Math.sin(s.lat * rad) + Math.cos(lat * rad) * Math.cos(s.lat * rad) * Math.cos((lon - s.lon) * rad);
  return 90 - Math.acos(Math.max(-1, Math.min(1, cosZ))) / rad;
}

/** The night side as a polygon ring of [lat, lon] pairs. */
export function nightPolygon(date: Date, stepDeg = 2): [number, number][] {
  const s = subsolarPoint(date);
  const dec = Math.abs(s.lat) < 0.01 ? 0.01 : s.lat; // avoid dividing by zero at the equinox
  const line: [number, number][] = [];
  for (let lon = -180; lon <= 180; lon += stepDeg) {
    const lat = Math.atan(-Math.cos((lon - s.lon) * rad) / Math.tan(dec * rad)) / rad;
    line.push([lat, lon]);
  }
  // Close around the pole that is in darkness.
  const pole = dec > 0 ? -90 : 90;
  return [...line, [pole, 180], [pole, -180]];
}
