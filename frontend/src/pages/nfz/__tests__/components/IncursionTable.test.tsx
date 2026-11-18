// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { IncursionTable } from "../../components/IncursionTable";
import { det } from "./fixtures";

afterEach(cleanup);

const base = { loading: false, hasData: true, selectedId: null, fresh: new Set<string>(), emptyMessage: "Sky is clear", onSelect: () => {} };

describe("<IncursionTable>", () => {
  it("lists incursions with aircraft, zone and type", () => {
    render(<IncursionTable {...base} rows={[det("a", 5), det("b", 9, { zone_id: "DEMO-1", zone_type: "PROHIBITED" })]} />);
    expect(screen.getAllByRole("row")).toHaveLength(3); // header + 2
    expect(screen.getByText("DEMO-1")).toBeTruthy();
    expect(screen.getByText("DEMO")).toBeTruthy(); // demo zones are badged
  });
  it("shows the empty message", () => {
    render(<IncursionTable {...base} rows={[]} />);
    expect(screen.getByText("Sky is clear")).toBeTruthy();
  });
  it("selects with a click or the Enter key", () => {
    const onSelect = vi.fn();
    render(<IncursionTable {...base} rows={[det("a", 5)]} onSelect={onSelect} />);
    const row = screen.getAllByRole("row")[1];
    fireEvent.click(row);
    fireEvent.keyDown(row, { key: "Enter" });
    expect(onSelect).toHaveBeenCalledTimes(2);
  });
  it("marks the selected row and new rows", () => {
    render(<IncursionTable {...base} rows={[det("a", 5)]} selectedId="a" fresh={new Set(["a"])} />);
    const row = screen.getAllByRole("row")[1];
    expect(row.getAttribute("aria-selected")).toBe("true");
    expect(row.className).toContain("nfz-row-new");
  });
  it("shows placeholder rows on first load", () => {
    const { container } = render(<IncursionTable {...base} rows={[]} loading hasData={false} />);
    expect(container.querySelectorAll(".nfz-skel--row").length).toBe(5);
  });
});
