// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { createRef } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FeedControls } from "../../components/FeedControls";
import { DEFAULT_STATE } from "../../urlState";

afterEach(cleanup);

function setup(over: Partial<Parameters<typeof FeedControls>[0]> = {}) {
  const props = {
    state: DEFAULT_STATE,
    update: vi.fn(),
    zoneTypes: ["MOA", "PROHIBITED"],
    loading: false,
    onRefresh: vi.fn(),
    onExport: vi.fn(),
    exportCount: 3,
    searchRef: createRef<HTMLInputElement>(),
    ...over,
  };
  render(<FeedControls {...props} />);
  return props;
}

describe("<FeedControls>", () => {
  it("changes the time range", () => {
    const p = setup();
    fireEvent.change(screen.getByLabelText(/time range/i), { target: { value: "6" } });
    expect(p.update).toHaveBeenCalledWith({ hours: 6 });
  });
  it("filters by zone type and searches", () => {
    const p = setup();
    fireEvent.change(screen.getByLabelText(/zone type/i), { target: { value: "MOA" } });
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "P-56" } });
    expect(p.update).toHaveBeenCalledWith({ zoneType: "MOA" });
    expect(p.update).toHaveBeenCalledWith({ search: "P-56" });
  });
  it("exports, but only when there's something to export", () => {
    const p = setup();
    fireEvent.click(screen.getByRole("button", { name: /export csv/i }));
    expect(p.onExport).toHaveBeenCalled();
    cleanup();
    setup({ exportCount: 0 });
    expect((screen.getByRole("button", { name: /export csv/i }) as HTMLButtonElement).disabled).toBe(true);
  });
});
