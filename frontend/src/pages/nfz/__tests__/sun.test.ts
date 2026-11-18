import { describe, expect, it } from "vitest";
import { nightPolygon, subsolarPoint, sunElevation } from "../map/sun";

describe("sun position", () => {
  it("puts the sun over the Tropic of Cancer at the June solstice", () => {
    const s = subsolarPoint(new Date("2026-06-21T12:00:00Z"));
    expect(s.lat).toBeGreaterThan(23.1);
    expect(s.lat).toBeLessThan(23.6);
    expect(Math.abs(s.lon)).toBeLessThan(3); // noon UTC: near Greenwich
  });
  it("puts the sun over the equator at the March equinox", () => {
    expect(Math.abs(subsolarPoint(new Date("2026-03-20T15:00:00Z")).lat)).toBeLessThan(0.6);
  });
  it("knows day from night in Lynchburg", () => {
    expect(sunElevation(37.33, -79.2, new Date("2026-06-21T17:00:00Z"))).toBeGreaterThan(60); // ~1 pm EDT
    expect(sunElevation(37.33, -79.2, new Date("2026-06-21T06:00:00Z"))).toBeLessThan(-10); // ~2 am EDT
  });
  it("draws the day/night line where the sun is on the horizon", () => {
    const date = new Date("2026-11-17T22:00:00Z");
    const ring = nightPolygon(date, 10);
    const line = ring.slice(0, -2);
    for (const [lat, lon] of line) {
      if (Math.abs(lat) > 80) continue;
      expect(Math.abs(sunElevation(lat, lon, date))).toBeLessThan(1);
    }
  });
});
