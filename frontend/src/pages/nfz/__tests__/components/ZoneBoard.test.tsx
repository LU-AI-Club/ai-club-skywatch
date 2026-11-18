// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ZoneBoard } from "../../components/ZoneBoard";
import { toZones, type ZoneFeature } from "../../zones";

afterEach(cleanup);

const feature = (zone_id: string, zone_type: string, activation = "ALWAYS"): ZoneFeature => ({
  type: "Feature",
  geometry: { type: "Polygon", coordinates: [[[-79.3, 37.3], [-79.2, 37.3], [-79.2, 37.4], [-79.3, 37.3]]] },
  properties: { zone_id, name: zone_id, zone_type, activation, floor_ft: 0, floor_datum: "SFC", ceiling_ft: 18000, ceiling_datum: "MSL" },
});
const zones = toZones([{ type: "FeatureCollection", features: [feature("P-56", "PROHIBITED"), feature("FARMVILLE MOA", "MOA", "SCHEDULED")] }]);

describe("<ZoneBoard>", () => {
  it("shows every zone with its count, type and schedule", () => {
    render(<ZoneBoard zones={zones} counts={new Map([["P-56", 4]])} focusId="" pinged={new Set()} onPick={() => {}} />);
    const p56 = screen.getByRole("button", { name: /P-56/ });
    expect(p56.textContent).toContain("4");
    expect(p56.textContent).toContain("PROHIBITED");
    expect(p56.textContent).toContain("ALWAYS");
    expect(p56.className).toContain("is-active"); // has incursions
    expect(screen.getByRole("button", { name: /FARMVILLE/ }).className).not.toContain("is-active");
  });
  it("picks a zone on click and marks the selected one", () => {
    const onPick = vi.fn();
    render(<ZoneBoard zones={zones} counts={new Map()} focusId="P-56" pinged={new Set()} onPick={onPick} />);
    fireEvent.click(screen.getByRole("button", { name: /FARMVILLE/ }));
    expect(onPick).toHaveBeenCalledWith("FARMVILLE MOA");
    expect(screen.getByRole("button", { name: /P-56/ }).getAttribute("aria-pressed")).toBe("true");
  });
  it("shows placeholders while the zone files load", () => {
    const { container } = render(<ZoneBoard zones={[]} counts={new Map()} focusId="" pinged={new Set()} onPick={() => {}} />);
    expect(container.querySelectorAll(".nfz-zone--skel").length).toBeGreaterThan(0);
  });
});
