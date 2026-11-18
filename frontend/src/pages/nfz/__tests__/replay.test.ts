import { describe, expect, it } from "vitest";
import { aircraftAt, historyStart, mergeTrack } from "../replay";
import type { AircraftMeta, Fix } from "../trails";

const T0 = Date.parse("2026-11-17T21:00:00Z");
const meta = new Map<string, AircraftMeta>([["a", { icao24: "a", callsign: "TEST1", squawk: "1200", category: "A3" }]]);

function store(fixes: Fix[]): Map<string, Fix[]> {
  return new Map([["a", fixes]]);
}

describe("aircraftAt (sky replay positions)", () => {
  const fixes: Fix[] = [
    { lat: 37, lon: -79, t: T0, alt: 1000, course: 90, sog: 120 },
    { lat: 37, lon: -78.9, t: T0 + 60_000, alt: 3000, course: 90, sog: 120 },
  ];
  it("interpolates position and altitude between fixes", () => {
    const [a] = aircraftAt(store(fixes), meta, T0 + 30_000);
    expect(a.geometry.coordinates[0]).toBeCloseTo(-78.95, 6);
    expect(Number(a.properties.altitude)).toBe(2000);
    expect(a.properties.callsign).toBe("TEST1");
    expect(a.properties.cog).toBeCloseTo(90, 0);
  });
  it("leaves out aircraft before their first fix or long after their last", () => {
    expect(aircraftAt(store(fixes), meta, T0 - 1)).toHaveLength(0);
    expect(aircraftAt(store(fixes), meta, T0 + 60_000 + 10_000)).toHaveLength(1); // just after: still shown
    expect(aircraftAt(store(fixes), meta, T0 + 60_000 + 5 * 60_000)).toHaveLength(0);
  });
  it("does not slide across a big gap (the plane left the feed): holds, then drops it", () => {
    const gap: Fix[] = [
      { lat: 37, lon: -79, t: T0 },
      { lat: 38, lon: -79, t: T0 + 120_000 }, // 60 nm in two minutes: a jump, not a flight
    ];
    const [held] = aircraftAt(store(gap), meta, T0 + 30_000);
    expect(held.geometry.coordinates[1]).toBe(37); // last real position, not halfway
    expect(aircraftAt(store(gap), meta, T0 + 60_000)).toHaveLength(0); // then it drops out
  });
});

describe("history helpers", () => {
  it("finds where recorded history starts", () => {
    expect(historyStart(new Map())).toBeNull();
    expect(historyStart(store([{ lat: 0, lon: 0, t: T0 + 5 }, { lat: 0, lon: 0, t: T0 + 9 }]))).toBe(T0 + 5);
  });
  it("merges a fetched track, thinned to one fix per 10 s, without duplicates", () => {
    const s = store([{ lat: 37, lon: -79, t: T0 }]);
    const pts = Array.from({ length: 61 }, (_, i) => ({ t: T0 + i * 1000, lat: 37, lon: -79 + i * 0.001, alt: 1000, sog: 100, course: 90 }));
    const added = mergeTrack(s, "a", pts, 10_000);
    expect(added).toBe(6); // 10 s, 20 s … 60 s (0 s was already there)
    const times = s.get("a")!.map((f) => f.t);
    expect(times).toEqual([...times].sort((x, y) => x - y));
  });
});
