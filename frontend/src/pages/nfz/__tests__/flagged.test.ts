import { describe, expect, it } from "vitest";
import type { Detection } from "../../../api/types";
import { buildFlagged, isRecent } from "../flagged";
import { emergencyOf } from "../squawk";
import { SEVERITY } from "../severity";

const now = Date.parse("2026-11-17T22:00:00Z");
const det = (id: string, entity: string, severity: string, minsAgo: number, open = false): Detection => ({
  detection_id: id,
  detector_id: "x",
  detector_version: "1",
  detection_type: "x",
  severity,
  confidence: 1,
  entity_id: entity,
  latitude: 37,
  longitude: -79,
  temporal_bounds_start: new Date(now - minsAgo * 60_000 - 60_000).toISOString(),
  temporal_bounds_end: open ? null : new Date(now - minsAgo * 60_000).toISOString(),
  last_detected_at: new Date(now - minsAgo * 60_000).toISOString(),
});

describe("flagged aircraft", () => {
  it("counts open or recent detections only", () => {
    expect(isRecent(det("a", "e", "low", 5), now)).toBe(true);
    expect(isRecent(det("a", "e", "low", 45), now)).toBe(false);
    expect(isRecent(det("a", "e", "low", 600, true), now)).toBe(true);
  });
  it("keeps the worst severity per aircraft", () => {
    const m = buildFlagged([det("1", "icao24:a", "low", 1), det("2", "icao24:a", "critical", 2), det("3", "icao24:b", "info", 3)], null, now);
    expect(m.get("icao24:a")).toMatchObject({ severity: "critical", color: SEVERITY.critical, count: 2 });
    expect(m.get("icao24:b")?.severity).toBe("info");
  });
  it("always includes the selected detection, even if old", () => {
    const m = buildFlagged([det("old", "icao24:c", "high", 600)], "old", now);
    expect(m.get("icao24:c")?.selected).toBe(true);
    expect(buildFlagged([det("old", "icao24:c", "high", 600)], null, now).size).toBe(0);
  });
});

describe("emergency squawks", () => {
  it("names the three emergency codes", () => {
    expect(emergencyOf("7700")).toBe("Emergency");
    expect(emergencyOf("7600")).toBe("Radio failure");
    expect(emergencyOf(" 7500 ")).toBe("Unlawful interference");
  });
  it("ignores ordinary codes", () => {
    expect(emergencyOf("1200")).toBeNull();
    expect(emergencyOf(null)).toBeNull();
  });
});
