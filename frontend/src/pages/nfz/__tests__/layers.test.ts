import { describe, expect, it } from "vitest";
import { DEFAULT_LAYERS, parseLayers } from "../map/LayerSwitch";
import { heatWeight } from "../severity";

describe("saved map layers", () => {
  it("starts calm: context layers off", () => {
    const l = parseLayers(null);
    expect(l).toEqual(DEFAULT_LAYERS);
    expect([l.weather, l.airports, l.navaids, l.daynight, l.heatmap]).toEqual([false, false, false, false, false]);
    expect(l.tags).toBe("key");
  });
  it("upgrades older saves where tags were true/false", () => {
    expect(parseLayers(JSON.stringify({ tags: false })).tags).toBe("off");
    expect(parseLayers(JSON.stringify({ tags: true })).tags).toBe("key");
    expect(parseLayers(JSON.stringify({ tags: "all", weather: true })).weather).toBe(true);
  });
  it("ignores junk", () => {
    expect(parseLayers("not json")).toEqual(DEFAULT_LAYERS);
    expect(parseLayers(JSON.stringify({ traffic: "yes" })).traffic).toBe(true);
  });
});

describe("heatmap weights", () => {
  it("weighs critical detections more than info", () => {
    expect(heatWeight("critical")).toBeGreaterThan(heatWeight("info"));
    expect(heatWeight("unknown")).toBeCloseTo(heatWeight("info"), 6);
  });
});
