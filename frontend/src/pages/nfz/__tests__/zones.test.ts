import { describe, expect, it } from "vitest";
import { altitudeRange, scheduleLabel, shapePath, toZones, zoneClass, type ZoneCollection } from "../zones";

const square = {
  type: "Feature",
  geometry: { type: "Polygon", coordinates: [[[-79.3, 37.3], [-79.2, 37.3], [-79.2, 37.4], [-79.3, 37.4], [-79.3, 37.3]]] },
  properties: {
    zone_id: "R-TEST",
    name: "R-TEST",
    zone_type: "restricted",
    activation: "NOTAM",
    times_of_use: "BY NOTAM",
    floor_ft: 0,
    floor_datum: "SFC",
    ceiling_ft: 18000,
    ceiling_datum: "FL",
    controlling_agency: null,
    source: "faa_sua",
    source_asof: "2026-09-28",
  },
};

describe("zone helpers", () => {
  it("classes zones for coloring", () => {
    expect(zoneClass("MOA")).toBe("moa");
    expect(zoneClass("moa")).toBe("moa");
    expect(zoneClass("PROHIBITED")).toBe("restricted");
    expect(zoneClass("RESTRICTED")).toBe("restricted");
  });
  it("labels schedules as published", () => {
    expect(scheduleLabel("ALWAYS")).toBe("ALWAYS");
    expect(scheduleLabel("scheduled")).toBe("SCHEDULED");
    expect(scheduleLabel("NOTAM")).toBe("NOTAM");
    expect(scheduleLabel("")).toBe("");
  });
});

describe("toZones", () => {
  it("reads one ZoneInfo per zone_id, first file wins", () => {
    const files: ZoneCollection[] = [
      { type: "FeatureCollection", features: [square] },
      { type: "FeatureCollection", features: [{ ...square, properties: { ...square.properties, name: "DUPLICATE" } }] },
    ];
    const zones = toZones(files);
    expect(zones).toHaveLength(1);
    const z = zones[0];
    expect(z.name).toBe("R-TEST");
    expect(z.type).toBe("RESTRICTED");
    expect(z.agency).toBe("");
    expect(z.source).toBe("faa_sua · 2026-09-28");
    expect(altitudeRange(z)).toBe("SFC–FL180");
  });
  it("marks demo zones", () => {
    const z = toZones([{ type: "FeatureCollection", features: [{ ...square, properties: { ...square.properties, zone_id: "DEMO-1" } }] }]);
    expect(z[0].demo).toBe(true);
  });
});

describe("shapePath", () => {
  it("fits the outline inside the box", () => {
    const d = shapePath(square, 34, 26)!;
    expect(d.startsWith("M")).toBe(true);
    expect(d.endsWith("Z")).toBe(true);
    const nums = d.match(/-?\d+(\.\d+)?/g)!.map(Number);
    const xs = nums.filter((_, i) => i % 2 === 0);
    const ys = nums.filter((_, i) => i % 2 === 1);
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...xs)).toBeLessThanOrEqual(34);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...ys)).toBeLessThanOrEqual(26);
  });
  it("keeps north at the top", () => {
    const d = shapePath(square, 34, 26)!;
    // The first point is the south-west corner, so it must be near the bottom.
    const [, y0] = d.slice(1).split(/[LZ]/)[0].split(" ").map(Number);
    expect(y0).toBeGreaterThan(13);
  });
  it("returns null without a usable geometry", () => {
    expect(shapePath(null, 34, 26)).toBeNull();
    expect(shapePath({ ...square, geometry: { type: "Point", coordinates: [0, 0] } }, 34, 26)).toBeNull();
  });
});
