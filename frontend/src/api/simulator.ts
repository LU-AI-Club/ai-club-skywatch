// Fake aircraft for working on the UI when nothing real is in the air (or the
// API isn't running). Frontend-only: when it's on, ObservationsProvider skips
// the API and reads from here instead, so every page sees the same fake feed.
//
// Turn it on by opening any page with ?simulate in the URL:
//   http://localhost:8081/map?simulate          40 aircraft, real-time
//   http://localhost:8081/map?simulate=150      150 aircraft
//   http://localhost:8081/map?simulate&simspeed=10   10x faster movement
//   http://localhost:8081/map?simulate=0        turn it back off
// The setting sticks for the browser tab, so in-app navigation keeps it.
import { config } from "../config";
import type { AircraftFeature } from "./types";
import type { TrackPoint } from "./tracks";

const STORAGE_KEY = "skywatch.simulate";
const DEFAULT_COUNT = 40;
// Aircraft that wander past this distance from the map center turn back.
const RADIUS_NM = 90;
const MAX_STALE_HOURS = 3;
const SIGNAL_LOSS_PER_SEC = 1.3e-5;
// Path history, so clicking a simulated plane shows where it has been.
const RECORD_EVERY_SEC = 10;
const MAX_HISTORY = 1500; // ~4 h at one point per 10 s
// Each new aircraft has already been flying this long (minutes), so it has a
// path to show the moment it appears.
const WARMUP_MIN = [10, 45] as const;

export interface SimulationSettings {
  count: number;
  speed: number; // time multiplier
}

// Reads ?simulate / ?simspeed from the URL (and remembers them for the tab).
// Returns null when simulation is off.
export function simulationSettings(): SimulationSettings | null {
  const params = new URLSearchParams(window.location.search);
  let stored: SimulationSettings | null = null;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) stored = JSON.parse(raw) as SimulationSettings;
  } catch {
    // Storage blocked or garbage — treat as not set.
  }

  if (!params.has("simulate")) return stored;

  const rawCount = params.get("simulate");
  const count = rawCount === "" || rawCount === null ? DEFAULT_COUNT : Number(rawCount);
  const speed = Number(params.get("simspeed") ?? stored?.speed ?? 1);
  const settings: SimulationSettings | null =
    Number.isFinite(count) && count > 0
      ? { count: Math.min(Math.round(count), 2000), speed: Number.isFinite(speed) && speed > 0 ? speed : 1 }
      : null;
  try {
    if (settings) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Not persisted; it still works for this page load.
  }
  return settings;
}

interface SimAircraft {
  icao24: string;
  callsign: string | null;
  lat: number;
  lon: number;
  altitudeFt: number | "ground";
  targetAltFt: number;
  speedKn: number;
  headingDeg: number;
  turnRateDegPerSec: number;
  squawk: string;
  category: string | null;
  // Altitude band this kind of aircraft wanders within.
  minAltFt: number;
  maxAltFt: number;
  // Stale aircraft are frozen at an old fix, so the map's age coloring shows.
  ageHours: number;
  history: TrackPoint[];
  sinceRecordSec: number;
}

const MAINLINE = ["AAL", "DAL", "UAL", "SWA", "JBU", "FDX", "UPS"];
const REGIONAL = ["RPA", "EDV", "ENY", "PDT", "UCA", "JIA", "SKW"];
const BIZJET = ["EJA", "LXJ", "GAJ"];

const rand = (min: number, max: number) => min + Math.random() * (max - min);
const pick = <T,>(items: readonly T[]): T => items[Math.floor(Math.random() * items.length)];
const wrap360 = (deg: number) => ((deg % 360) + 360) % 360;

function randomHex(): string {
  return Math.floor(Math.random() * 0xffffff)
    .toString(16)
    .padStart(6, "0");
}

const flightNumber = (prefixes: readonly string[]) =>
  `${pick(prefixes)}${Math.floor(rand(100, 9999))}`;

function nNumber(): string {
  const letters = "ABCDEFGHJKLMNPQRSTUVWXYZ";
  return `N${Math.floor(rand(100, 999))}${pick([...letters])}${pick([...letters])}`;
}

// Some aircraft don't broadcast a callsign at all.
const maybe = (callsign: string, chance = 0.9) => (Math.random() < chance ? callsign : null);

// The kinds of aircraft the simulator flies, roughly in the proportions the
// live Lynchburg feed shows. Each sets size category, callsign style, and a
// believable altitude and speed range.
interface SimKind {
  weight: number;
  category: string | null;
  callsign: () => string | null;
  altFt: [number, number];
  speedKn: [number, number];
}

const KINDS: SimKind[] = [
  // Mainline and cargo jets
  { weight: 45, category: "A3", callsign: () => maybe(flightNumber(MAINLINE), 0.85), altFt: [8000, 39000], speedKn: [300, 480] },
  { weight: 5, category: "A5", callsign: () => flightNumber(MAINLINE), altFt: [20000, 41000], speedKn: [380, 500] },
  { weight: 2, category: "A4", callsign: () => flightNumber(MAINLINE), altFt: [15000, 39000], speedKn: [350, 480] },
  // Regional jets (A2 with an airline callsign)
  { weight: 10, category: "A2", callsign: () => flightNumber(REGIONAL), altFt: [6000, 35000], speedKn: [250, 420] },
  // Business jets (A2 with a private operator or tail-number callsign)
  { weight: 8, category: "A2", callsign: () => (Math.random() < 0.6 ? flightNumber(BIZJET) : maybe(nNumber())), altFt: [10000, 43000], speedKn: [300, 470] },
  // Light general aviation
  { weight: 18, category: "A1", callsign: () => maybe(nNumber(), 0.8), altFt: [1500, 12000], speedKn: [90, 170] },
  // Helicopters: low and slow
  { weight: 4, category: "A7", callsign: () => maybe(nNumber(), 0.8), altFt: [500, 3500], speedKn: [70, 140] },
  // No category reported
  { weight: 5, category: null, callsign: () => null, altFt: [2000, 30000], speedKn: [120, 400] },
];
const KIND_TOTAL = KINDS.reduce((sum, k) => sum + k.weight, 0);

function pickKind(): SimKind {
  let r = Math.random() * KIND_TOTAL;
  for (const k of KINDS) {
    r -= k.weight;
    if (r <= 0) return k;
  }
  return KINDS[0];
}

// Destination point from (lat, lon) after travelling `nm` on `headingDeg`.
// Flat-earth approximation — plenty for a few hundred nautical miles.
function move(lat: number, lon: number, headingDeg: number, nm: number): [number, number] {
  const h = (headingDeg * Math.PI) / 180;
  const dLat = (nm * Math.cos(h)) / 60;
  const dLon = (nm * Math.sin(h)) / (60 * Math.cos((lat * Math.PI) / 180));
  return [lat + dLat, lon + dLon];
}

function distanceNm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = (lat2 - lat1) * 60;
  const dLon = (lon2 - lon1) * 60 * Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180);
  return Math.hypot(dLat, dLon);
}

function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const dLat = lat2 - lat1;
  const dLon = (lon2 - lon1) * Math.cos((((lat1 + lat2) / 2) * Math.PI) / 180);
  return wrap360((Math.atan2(dLon, dLat) * 180) / Math.PI);
}

function spawn(center: [number, number]): SimAircraft {
  const [lat, lon] = move(center[0], center[1], rand(0, 360), Math.sqrt(Math.random()) * RADIUS_NM);
  const kind = pickKind();
  const [minAltFt, maxAltFt] = kind.altFt;
  // ~5% are taxiing on the ground.
  if (Math.random() < 0.05) {
    return {
      icao24: randomHex(), callsign: kind.callsign(), lat, lon,
      altitudeFt: "ground", targetAltFt: 0, speedKn: rand(0, 20), headingDeg: rand(0, 360),
      turnRateDegPerSec: 0, squawk: "1200", category: kind.category,
      minAltFt, maxAltFt, ageHours: 0, history: [], sinceRecordSec: 0,
    };
  }
  const alt = rand(minAltFt, maxAltFt);
  const stale = Math.random() < 0.12;
  return {
    icao24: randomHex(),
    callsign: kind.callsign(),
    lat,
    lon,
    altitudeFt: Math.round(alt / 100) * 100,
    targetAltFt: alt,
    speedKn: rand(kind.speedKn[0], kind.speedKn[1]),
    headingDeg: rand(0, 360),
    turnRateDegPerSec: 0,
    // Squawks are 4 octal digits (0–7); a rare 7700 is an emergency.
    squawk: Math.random() < 0.01 ? "7700" : Math.floor(rand(0o1000, 0o7000)).toString(8),
    category: kind.category,
    minAltFt,
    maxAltFt,
    // A slice of the fleet is old fixes: 0.2–3 h stale, so they show faded.
    ageHours: stale ? rand(0.2, 3) : 0,
    history: [],
    sinceRecordSec: 0,
  };
}

function record(a: SimAircraft, clockMs: number): void {
  a.history.push({
    lat: a.lat,
    lon: a.lon,
    altitude: a.altitudeFt === "ground" ? "ground" : String(a.altitudeFt),
    observedAt: new Date(clockMs).toISOString(),
  });
  if (a.history.length > MAX_HISTORY) a.history.splice(0, a.history.length - MAX_HISTORY);
  a.sinceRecordSec = 0;
}

// A new aircraft, already some way into its flight: fly it forward from its
// spawn point while recording, so it arrives with a path behind it.
function spawnWithHistory(center: [number, number], nowMs: number): SimAircraft {
  const a = spawn(center);
  const finalAge = a.ageHours;
  a.ageHours = 0; // stale ones fly normally until their signal "drops"
  const warmupSec = rand(WARMUP_MIN[0], WARMUP_MIN[1]) * 60;
  for (let t = 0; t < warmupSec; t += RECORD_EVERY_SEC) {
    record(a, nowMs - (warmupSec - t) * 1000);
    step(a, RECORD_EVERY_SEC, center);
  }
  record(a, nowMs);
  if (finalAge > 0) a.ageHours = finalAge;
  return a;
}

function step(a: SimAircraft, dtSec: number, center: [number, number]): void {
  if (a.ageHours > 0) {
    a.ageHours += dtSec / 3600; // stale: doesn't move, just keeps aging
    return;
  }
  if (a.altitudeFt === "ground") {
    [a.lat, a.lon] = move(a.lat, a.lon, a.headingDeg, (a.speedKn * dtSec) / 3600);
    if (Math.random() < 0.02 * dtSec) a.headingDeg = wrap360(a.headingDeg + rand(-90, 90));
    return;
  }

  // Now and then an aircraft stops reporting and freezes at its last fix.
  // This rate keeps roughly 1 in 8 of the fleet faded over a long run.
  if (Math.random() < SIGNAL_LOSS_PER_SEC * dtSec) {
    a.ageHours = 1 / 3600;
    return;
  }

  // Occasionally start or stop a gentle turn (standard rate is 3°/s).
  if (Math.random() < 0.03 * dtSec) {
    a.turnRateDegPerSec = Math.random() < 0.5 ? 0 : rand(-2, 2);
  }
  // Heading out of the area? Turn back toward the center.
  if (distanceNm(a.lat, a.lon, center[0], center[1]) > RADIUS_NM) {
    const home = bearingDeg(a.lat, a.lon, center[0], center[1]);
    const diff = ((home - a.headingDeg + 540) % 360) - 180;
    a.turnRateDegPerSec = Math.sign(diff) * 3;
  }
  a.headingDeg = wrap360(a.headingDeg + a.turnRateDegPerSec * dtSec);

  // Drift altitude toward a target that occasionally changes.
  if (Math.random() < 0.01 * dtSec) a.targetAltFt = rand(a.minAltFt, a.maxAltFt);
  const climb = Math.max(-30, Math.min(30, (a.targetAltFt - a.altitudeFt) / 10)) * dtSec;
  a.altitudeFt = Math.round((a.altitudeFt + climb) / 25) * 25;

  [a.lat, a.lon] = move(a.lat, a.lon, a.headingDeg, (a.speedKn * dtSec) / 3600);
}

function toFeature(a: SimAircraft, now: Date): AircraftFeature {
  const observedAt = new Date(now.getTime() - a.ageHours * 3600_000).toISOString();
  return {
    type: "Feature",
    id: a.icao24,
    geometry: { type: "Point", coordinates: [a.lon, a.lat] },
    properties: {
      icao24: a.icao24,
      callsign: a.callsign,
      altitude: a.altitudeFt === "ground" ? "ground" : String(a.altitudeFt),
      squawk: a.squawk,
      category: a.category,
      sog: a.speedKn,
      cog: a.headingDeg,
      heading: a.headingDeg,
      latitude: a.lat,
      longitude: a.lon,
      observed_at: observedAt,
      position_age_hours: a.ageHours,
      source_id: "simulator",
    },
  };
}

export interface Simulation {
  // Advance the world by `dtSec` real seconds and return the current snapshot.
  tick(dtSec: number): AircraftFeature[];
}

// The running simulation's fleet, so simulatedTrack() can read paths.
let activeFleet: SimAircraft[] | null = null;

export function createSimulation({ count, speed }: SimulationSettings): Simulation {
  const center = config.mapCenter;
  const fleet = Array.from({ length: count }, () => spawnWithHistory(center, Date.now()));
  activeFleet = fleet;
  return {
    tick(dtSec) {
      const simDt = dtSec * speed;
      const nowMs = Date.now();
      for (let i = 0; i < fleet.length; i++) {
        const a = fleet[i];
        step(a, simDt, center);
        a.sinceRecordSec += simDt;
        if (a.ageHours === 0 && a.sinceRecordSec >= RECORD_EVERY_SEC) record(a, nowMs);
        // Real feeds drop very old fixes; swap them for a new aircraft.
        if (a.ageHours > MAX_STALE_HOURS) fleet[i] = spawnWithHistory(center, nowMs);
      }
      const now = new Date(nowMs);
      return fleet.map((a) => toFeature(a, now));
    },
  };
}

// A simulated aircraft's path, oldest first, ending at its current position.
// Returns null when simulation is off, so callers fall back to the API.
export function simulatedTrack(icao24: string): TrackPoint[] | null {
  if (!activeFleet) return null;
  const a = activeFleet.find((x) => x.icao24 === icao24);
  if (!a) return [];
  const points = [...a.history];
  const last = points[points.length - 1];
  if (!last || last.lat !== a.lat || last.lon !== a.lon) {
    points.push({
      lat: a.lat,
      lon: a.lon,
      altitude: a.altitudeFt === "ground" ? "ground" : String(a.altitudeFt),
      observedAt: new Date().toISOString(),
    });
  }
  return points;
}
