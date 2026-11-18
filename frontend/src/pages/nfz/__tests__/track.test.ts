import { describe, expect, it } from "vitest";
import { bearing, parseTrack, sampleTrack, windowTrack } from "../track";

const base = Date.parse("2026-11-17T21:00:00Z");
const res = {
  geometry: { coordinates: [[-79, 37], [-78.9, 37], [-78.8, 37]] as [number, number][] },
  properties: {
    points: [
      { observed_at: new Date(base + 20_000).toISOString(), latitude: 37, longitude: -78.8, altitude: "3000", sog: 200, cog: 90 },
      { observed_at: new Date(base).toISOString(), latitude: 37, longitude: -79, altitude: "1000", sog: 200, cog: 90 },
      { observed_at: new Date(base + 10_000).toISOString(), latitude: 37, longitude: -78.9, altitude: "ground", sog: null, cog: null, heading: 95 },
      { observed_at: "bad", latitude: 1, longitude: 2 },
    ],
  },
};

describe("parseTrack", () => {
  it("sorts by time, skips bad rows, and reads altitude", () => {
    const pts = parseTrack(res);
    expect(pts).toHaveLength(3);
    expect(pts.map((p) => p.lon)).toEqual([-79, -78.9, -78.8]);
    expect(pts[1].alt).toBe(0);
    expect(pts[1].course).toBe(95); // falls back to heading
  });
});

describe("sampleTrack", () => {
  const pts = parseTrack(res);
  it("interpolates between fixes", () => {
    const s = sampleTrack(pts, base + 5_000)!;
    expect(s.lon).toBeCloseTo(-78.95, 6);
    expect(s.alt).toBeCloseTo(500, 6);
    expect(s.index).toBe(0);
  });
  it("clamps before the start and after the end", () => {
    expect(sampleTrack(pts, base - 1)!.lon).toBe(-79);
    expect(sampleTrack(pts, base + 999_999)!.lon).toBe(-78.8);
  });
  it("returns null for an empty track", () => {
    expect(sampleTrack([], base)).toBeNull();
  });
});

describe("windowTrack and bearing", () => {
  it("keeps the part around the incursion", () => {
    const pts = parseTrack(res);
    // Only one fix falls inside this window, so the whole track comes back.
    expect(windowTrack(pts, base + 10_000, base + 10_000, 6_000)).toHaveLength(3);
    expect(windowTrack(pts, base + 5_000, base + 15_000, 6_000)).toHaveLength(3);
  });
  it("measures bearings clockwise from north", () => {
    expect(bearing({ lat: 37, lon: -79 }, { lat: 38, lon: -79 })).toBeCloseTo(0, 6);
    expect(bearing({ lat: 37, lon: -79 }, { lat: 37, lon: -78 })).toBeCloseTo(90, 6);
  });
});
