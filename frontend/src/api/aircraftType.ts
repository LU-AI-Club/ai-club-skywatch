// Rough aircraft type from ADS-B data, for the map's type filter.
//
// ADS-B doesn't say "passenger" or "private". What it has is the emitter
// category (size/kind) and the callsign, so this combines the two:
//   A1 light · A2 small/medium · A3 large · A4 large high-vortex (757)
//   A5 heavy · A6 high performance · A7 rotorcraft · B* gliders/balloons/drones
//   C* ground vehicles
// A2 mixes regional airliners (PDT, UCA, JIA…) with business jets (EJA…), so
// the callsign settles those. It's a best guess: e.g. military transports with
// airline-style callsigns land in "Airliners".
import type { AircraftProperties } from "./types";

// Marker colors are chosen to stay distinct from the map's other layers:
// detections (purple / cyan / amber), zones (red / orange / yellow fills) and
// the selected path (pink).
export const AIRCRAFT_TYPES = [
  { key: "airliner", label: "Airliners (passenger & cargo)", color: "#60a5fa" },
  { key: "private", label: "Private & small planes", color: "#4ade80" },
  { key: "helicopter", label: "Helicopters", color: "#fb923c" },
  { key: "other", label: "Other / unknown", color: "#cbd5e1" },
] as const;

export type AircraftType = (typeof AIRCRAFT_TYPES)[number]["key"];

// ICAO codes of fractional / private-jet operators, whose flights use
// airline-style callsigns but aren't airlines.
const PRIVATE_OPERATORS = new Set([
  "EJA", // NetJets
  "EJM", // Executive Jet Management
  "LXJ", // Flexjet
  "GAJ", // Wheels Up
  "XOJ", // XOJET
  "JTL", // Jet Linx
  "VJT", // VistaJet
]);

const AIRLINE_CALLSIGN = /^[A-Z]{3}\d/; // e.g. DAL1717
const N_NUMBER = /^N\d/; // US-registered tail number, e.g. N123AB

export function classifyAircraft(p: Pick<AircraftProperties, "category" | "callsign">): AircraftType {
  const cat = (p.category ?? "").trim().toUpperCase();
  const callsign = (p.callsign ?? "").trim().toUpperCase();

  if (cat === "A7") return "helicopter";
  if (N_NUMBER.test(callsign) || PRIVATE_OPERATORS.has(callsign.slice(0, 3))) return "private";
  if (cat === "A3" || cat === "A4" || cat === "A5") return "airliner";
  if (cat === "A2" && AIRLINE_CALLSIGN.test(callsign)) return "airliner";
  if (cat === "A1" || cat === "A2" || cat === "A6") return "private";
  return "other";
}

export function aircraftTypeInfo(type: AircraftType) {
  return AIRCRAFT_TYPES.find((t) => t.key === type)!;
}

export function aircraftTypeLabel(type: AircraftType): string {
  return aircraftTypeInfo(type).label;
}
