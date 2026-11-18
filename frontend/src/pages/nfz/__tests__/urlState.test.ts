import { describe, expect, it } from "vitest";
import { DEFAULT_STATE, parseState, serializeState } from "../urlState";

describe("URL state", () => {
  it("round-trips a shared link", () => {
    const state = { hours: 6, severity: "high", zoneType: "MOA", search: "a1b2", zone: "P-56", selected: "abc" };
    expect(parseState(serializeState(state))).toEqual(state);
  });
  it("leaves defaults out to keep links short", () => {
    expect(serializeState(DEFAULT_STATE).toString()).toBe("");
    expect(serializeState({ ...DEFAULT_STATE, zone: "P-56" }).toString()).toBe("zone=P-56");
  });
  it("ignores values that aren't allowed", () => {
    const s = parseState(new URLSearchParams("h=13&sev=apocalyptic"));
    expect(s.hours).toBe(DEFAULT_STATE.hours);
    expect(s.severity).toBe("");
  });
  it("caps very long values", () => {
    const s = parseState(new URLSearchParams(`q=${"x".repeat(500)}`));
    expect(s.search.length).toBe(100);
  });
});
