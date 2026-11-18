import { describe, expect, it } from "vitest";
import { ago, dms, duration, gridLabel, zuluClock, zuluDay, zuluShort, zuluStamp, zuluTime } from "../format";

const T = "2026-11-17T21:42:05Z";

describe("Zulu time", () => {
  it("formats in UTC regardless of the computer's time zone", () => {
    expect(zuluTime(T)).toBe("17 NOV 21:42:05Z");
    expect(zuluShort(T)).toBe("21:42Z");
    expect(zuluClock(T)).toBe("21:42:05Z");
    expect(zuluDay(T)).toBe("17 NOV");
    expect(zuluStamp(T)).toBe("20261117T2142Z");
  });
  it("accepts numbers and Dates", () => {
    const ms = Date.parse(T);
    expect(zuluShort(ms)).toBe("21:42Z");
    expect(zuluShort(new Date(ms))).toBe("21:42Z");
  });
  it("shows a dash for missing or invalid times", () => {
    expect(zuluTime(null)).toBe("—");
    expect(zuluTime("not a date")).toBe("—");
    expect(zuluShort(undefined)).toBe("—");
  });
});

describe("ago", () => {
  const now = Date.parse(T);
  it("picks the right unit", () => {
    expect(ago(now - 45_000, now)).toBe("45s ago");
    expect(ago(now - 3 * 60_000, now)).toBe("3 min ago");
    expect(ago(now - 2 * 3_600_000, now)).toBe("2 h ago");
    expect(ago(now - 4 * 86_400_000, now)).toBe("4 d ago");
  });
  it("never goes negative for times slightly in the future", () => {
    expect(ago(now + 5000, now)).toBe("0s ago");
  });
});

describe("duration", () => {
  it("formats seconds", () => {
    expect(duration(42)).toBe("42 s");
    expect(duration(277)).toBe("4 m 37 s");
    expect(duration("90")).toBe("1 m 30 s");
  });
  it("shows a dash for nothing", () => {
    expect(duration(null)).toBe("—");
    expect(duration(undefined)).toBe("—");
    expect(duration("")).toBe("—");
    expect(duration("abc")).toBe("—");
  });
});

describe("chart coordinates", () => {
  it("formats degrees-minutes-seconds like a chart", () => {
    expect(dms(37.3267, "lat")).toBe(`37°19'36"N`);
    expect(dms(-79.2011, "lon")).toBe(`079°12'04"W`);
  });
  it("rolls 60 seconds over into the next minute", () => {
    expect(dms(37.99999, "lat")).toBe(`38°00'00"N`);
  });
  it("labels grid lines", () => {
    expect(gridLabel(37.5, "lat")).toBe("37°30'N");
    expect(gridLabel(-79, "lon")).toBe("79°W");
    expect(gridLabel(37 + 10 / 60, "lat")).toBe("37°10'N");
  });
});
