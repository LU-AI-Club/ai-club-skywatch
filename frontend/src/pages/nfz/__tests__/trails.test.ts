import { describe, expect, it } from "vitest";
import type { AircraftFeature } from "../../../api/types";
import { MAX_JUMP_NM, TRAIL_MINUTES, recordFixes, trailRuns, trendArrow, verticalRate, type Fix } from "../trails";
import { nmBetween, project } from "../geo";

function plane(id: string, lat: number, lon: number, iso: string): AircraftFeature {
  return {
    type: "Feature",
    id,
    geometry: { type: "Point", coordinates: [lon, lat] },
    properties: {
      icao24: id,
      callsign: null,
      altitude: "5000",
      squawk: null,
      category: null,
      sog: 200,
      cog: 90,
      heading: 90,
      latitude: lat,
      longitude: lon,
      observed_at: iso,
      position_age_hours: 0,
      source_id: "test",
    },
  };
}

describe("geo", () => {
  it("projects and measures in nautical miles", () => {
    const a = { lat: 37.3, lon: -79.2 };
    const b = project(a, 90, 10);
    expect(nmBetween(a, b)).toBeCloseTo(10, 5);
    expect(project(a, 0, 60).lat).toBeCloseTo(38.3, 6); // 60 nm north = 1 degree
  });
});

describe("recordFixes", () => {
  it("appends new positions and skips repeats", () => {
    const store = new Map<string, Fix[]>();
    recordFixes([plane("a", 37, -79, "2026-11-17T21:00:00Z")], store);
    recordFixes([plane("a", 37, -79, "2026-11-17T21:00:00Z")], store); // same fix again
    recordFixes([plane("a", 37.01, -79, "2026-11-17T21:00:10Z")], store);
    expect(store.get("a")).toHaveLength(2);
  });
  it(`keeps only the last ${TRAIL_MINUTES} minutes`, () => {
    const store = new Map<string, Fix[]>();
    recordFixes([plane("a", 37, -79, "2026-11-17T21:00:00Z")], store);
    recordFixes([plane("a", 37.01, -79, "2026-11-17T21:20:00Z")], store);
    expect(store.get("a")).toHaveLength(1);
  });
  it("forgets aircraft that have been gone a long time", () => {
    const store = new Map<string, Fix[]>();
    recordFixes([plane("gone", 37, -79, "2026-11-17T20:00:00Z")], store);
    recordFixes([plane("here", 37, -79, "2026-11-17T21:00:00Z")], store);
    expect(store.has("gone")).toBe(false);
    expect(store.has("here")).toBe(true);
  });
});

describe("trailRuns", () => {
  const t = (i: number) => Date.parse("2026-11-17T21:00:00Z") + i * 10_000;
  const along = (n: number, stepNm: number): Fix[] =>
    Array.from({ length: n }, (_, i) => ({ ...project({ lat: 37, lon: -79 }, 90, i * stepNm), t: t(i) }));

  it("fades from oldest (age 0) to newest (age 2)", () => {
    const runs = trailRuns(along(10, 1));
    expect(runs[0].age).toBe(0);
    expect(runs[runs.length - 1].age).toBe(2);
    // consecutive runs share their joining point, so the line has no gaps
    expect(runs[1].points[0]).toEqual(runs[0].points[runs[0].points.length - 1]);
  });
  it(`breaks the line at a jump bigger than ${MAX_JUMP_NM} nm`, () => {
    const a = along(4, 1);
    const far = along(4, 1).map((f, i) => ({ ...project(f, 0, 30), t: t(10 + i) }));
    const runs = trailRuns([...a, ...far]);
    for (const r of runs) {
      for (let i = 1; i < r.points.length; i++) {
        const [la, lo] = r.points[i - 1];
        const [lb, lb2] = r.points[i];
        expect(nmBetween({ lat: la, lon: lo }, { lat: lb, lon: lb2 })).toBeLessThanOrEqual(MAX_JUMP_NM);
      }
    }
  });
  it("needs at least two fixes", () => {
    expect(trailRuns([])).toEqual([]);
    expect(trailRuns(along(1, 1))).toEqual([]);
  });
});

describe("verticalRate", () => {
  const at = (sec: number, alt: number | null): Fix => ({ lat: 37, lon: -79, t: sec * 1000, alt });
  it("measures climbs and descents in feet per minute", () => {
    expect(verticalRate([at(0, 3000), at(30, 3500), at(60, 4000)])).toBeCloseTo(1000, 6);
    expect(verticalRate([at(0, 9000), at(60, 8000)])).toBeCloseTo(-1000, 6);
  });
  it("needs at least 20 seconds of history with altitudes", () => {
    expect(verticalRate([at(0, 3000), at(10, 3100)])).toBeNull();
    expect(verticalRate([at(0, null), at(60, 3000)])).toBeNull();
    expect(verticalRate([])).toBeNull();
  });
  it("draws an arrow only for real climbs or descents", () => {
    expect(trendArrow(1200)).toBe("↑");
    expect(trendArrow(-800)).toBe("↓");
    expect(trendArrow(100)).toBe("");
    expect(trendArrow(null)).toBe("");
  });
});
