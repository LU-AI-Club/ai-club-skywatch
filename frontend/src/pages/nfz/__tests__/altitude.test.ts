import { describe, expect, it } from "vitest";
import { ALTITUDE_BANDS, GRAY, altitudeColor, altitudeFt, altitudeTag, limitLabel } from "../altitude";

describe("altitudeFt", () => {
  it("reads the feed's text altitudes", () => {
    expect(altitudeFt("35000")).toBe(35000);
    expect(altitudeFt("ground")).toBe(0);
    expect(altitudeFt(" Ground ")).toBe(0);
    expect(altitudeFt(4200)).toBe(4200);
  });
  it("returns null for nothing usable", () => {
    expect(altitudeFt(null)).toBeNull();
    expect(altitudeFt("")).toBeNull();
    expect(altitudeFt("n/a")).toBeNull();
  });
});

describe("altitudeColor", () => {
  it("uses the band the altitude falls in", () => {
    expect(altitudeColor(2000)).toBe(ALTITUDE_BANDS[0].color);
    expect(altitudeColor(5000)).toBe(ALTITUDE_BANDS[1].color); // 5,000 is the start of band 2
    expect(altitudeColor(25000)).toBe(ALTITUDE_BANDS[2].color);
    expect(altitudeColor(41000)).toBe(ALTITUDE_BANDS[3].color);
  });
  it("is gray on the ground, unknown, or stale", () => {
    expect(altitudeColor(0)).toBe(GRAY);
    expect(altitudeColor(null)).toBe(GRAY);
    expect(altitudeColor(12000, true)).toBe(GRAY);
  });
});

describe("altitudeTag (ATC data tag)", () => {
  it("shows hundreds of feet, padded to three digits", () => {
    expect(altitudeTag(35000)).toBe("350");
    expect(altitudeTag(4200)).toBe("042");
    expect(altitudeTag(0)).toBe("GND");
    expect(altitudeTag(null)).toBe("---");
  });
});

describe("limitLabel (zone floor/ceiling)", () => {
  it("prints limits the way a sectional chart does", () => {
    expect(limitLabel(0, "SFC")).toBe("SFC");
    expect(limitLabel(500, "AGL")).toBe("500 AGL");
    expect(limitLabel(11000, "MSL")).toBe("11,000");
    expect(limitLabel(18000, "FL")).toBe("FL180");
    expect(limitLabel(null, "MSL")).toBe("—");
  });
});
