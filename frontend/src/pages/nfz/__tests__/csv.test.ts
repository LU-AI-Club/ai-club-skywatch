import { describe, expect, it } from "vitest";
import type { Detection } from "../../../api/types";
import { CSV_COLUMNS, csvCell, summaryOf, toCsv } from "../csv";

const d = {
  detection_id: "d1",
  detector_id: "skywatch.no_fly_zone",
  detector_version: "1",
  detection_type: "nfz",
  severity: "high",
  confidence: 0.9,
  entity_id: "icao24:a1b2c3",
  latitude: 37.3,
  longitude: -79.2,
  temporal_bounds_start: "2026-11-17T21:00:00Z",
  temporal_bounds_end: null,
  last_detected_at: "2026-11-17T21:01:00Z",
  zone_id: "P-56",
  zone_name: "P-56, the Mall",
  zone_type: "PROHIBITED",
  duration_seconds: 60,
  evidence: { summary: 'Entered "P-56"' },
} as Detection;

describe("csvCell", () => {
  it("quotes commas, quotes and newlines", () => {
    expect(csvCell("a,b")).toBe('"a,b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell("two\nlines")).toBe('"two\nlines"');
  });
  it("stops spreadsheet formulas from running", () => {
    expect(csvCell("=HYPERLINK(1)")).toBe("'=HYPERLINK(1)");
    expect(csvCell("+1")).toBe("'+1");
    expect(csvCell("@x")).toBe("'@x");
  });
  it("leaves numbers alone, including negative ones", () => {
    expect(csvCell(-79.2)).toBe("-79.2");
    expect(csvCell(0)).toBe("0");
  });
  it("writes nothing for null", () => {
    expect(csvCell(null)).toBe("");
    expect(csvCell(undefined)).toBe("");
  });
});

describe("toCsv", () => {
  it("has a header and one line per detection", () => {
    const lines = toCsv([d]).trim().split("\r\n");
    expect(lines[0]).toBe(CSV_COLUMNS.join(","));
    expect(lines).toHaveLength(2);
    expect(lines[1]).toContain('"P-56, the Mall"');
    expect(lines[1]).toContain('"Entered ""P-56"""');
  });
  it("finds the detector's summary", () => {
    expect(summaryOf(d)).toBe('Entered "P-56"');
    expect(summaryOf({ ...d, evidence: "plain text" })).toBe("plain text");
    expect(summaryOf({ ...d, evidence: { other: 1 } })).toBeNull();
  });
});
