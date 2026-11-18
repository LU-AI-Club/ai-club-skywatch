import { describe, expect, it } from "vitest";
import { placeTags, slotBox, tagSize, type TagRequest } from "../map/labels";

const req = (id: string, x: number, y: number, extra: Partial<TagRequest> = {}): TagRequest => ({
  id, x, y, w: 60, h: 30, priority: 0, force: false, ...extra,
});

describe("data-tag placement", () => {
  it("uses the default NE spot when there is room", () => {
    expect(placeTags([req("a", 100, 100)]).get("a")).toBe("ne");
  });
  it("moves a second tag to another spot instead of overlapping", () => {
    const out = placeTags([req("a", 100, 100, { priority: 2 }), req("b", 104, 102, { priority: 1 })]);
    expect(out.get("a")).toBe("ne");
    expect(["nw", "se", "sw"]).toContain(out.get("b"));
  });
  it("hides a tag when all four spots are taken", () => {
    const crowd = [req("a", 100, 100, { priority: 9 }), req("b", 101, 100, { priority: 8 }), req("c", 99, 101, { priority: 7 }), req("d", 100, 99, { priority: 6 }), req("e", 100, 100, { priority: 1 })];
    expect(placeTags(crowd).get("e")).toBe("off");
  });
  it("always shows forced tags (selected, emergency, flagged)", () => {
    const crowd = [req("a", 100, 100, { priority: 9 }), req("b", 101, 100, { priority: 8 }), req("c", 99, 101, { priority: 7 }), req("d", 100, 99, { priority: 6 }), req("e", 100, 100, { priority: 1, force: true })];
    expect(placeTags(crowd).get("e")).not.toBe("off");
  });
  it("keeps last time's spot when it still fits (no jumping)", () => {
    expect(placeTags([req("a", 100, 100, { prev: "sw" })]).get("a")).toBe("sw");
  });
  it("places boxes on the correct side of the plane", () => {
    const r = { x: 100, y: 100, w: 60, h: 30 };
    expect(slotBox(r, "ne").x).toBeGreaterThan(100);
    expect(slotBox(r, "nw").x + 60).toBeLessThan(100);
    expect(slotBox(r, "se").y).toBeGreaterThan(slotBox(r, "ne").y);
  });
  it("estimates tag size from the callsign", () => {
    expect(tagSize("DAL1729", 2).w).toBeGreaterThan(tagSize("N1", 2).w - 1);
    expect(tagSize("X", 3).h).toBeGreaterThan(tagSize("X", 2).h);
  });
});
