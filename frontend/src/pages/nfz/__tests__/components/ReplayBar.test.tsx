// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ReplayBar } from "../../components/ReplayBar";
import { NOW, det } from "./fixtures";

afterEach(cleanup);

function setup(over: Partial<Parameters<typeof ReplayBar>[0]> = {}) {
  const props = {
    t: NOW - 20 * 60_000,
    now: NOW,
    playing: false,
    speed: 30 as const,
    historyFrom: NOW - 40 * 60_000,
    detections: [det("in-window", 10), det("too-old", 90)],
    loading: null,
    inView: 12,
    onToggle: vi.fn(),
    onSeek: vi.fn(),
    onSpeed: vi.fn(),
    onLoad: vi.fn(),
    onClose: vi.fn(),
    ...over,
  };
  render(<ReplayBar {...props} />);
  return props;
}

describe("<ReplayBar>", () => {
  it("marks detections from the last hour; clicking one jumps just before it", () => {
    const p = setup();
    const marks = screen.getAllByRole("button", { name: /jump to/i });
    expect(marks).toHaveLength(1); // the 90-minute-old one is outside the hour
    fireEvent.click(marks[0]);
    const start = Date.parse(det("in-window", 10).temporal_bounds_start);
    expect(p.onSeek).toHaveBeenCalledWith(start - 30_000);
  });
  it("shows how far back it is, and plays, changes speed, loads history, goes live", () => {
    const p = setup();
    expect(screen.getByText("−20 min")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /play sky replay/i }));
    fireEvent.click(screen.getByRole("button", { name: "60×" }));
    fireEvent.click(screen.getByRole("button", { name: /history.*\(12\)/i }));
    fireEvent.click(screen.getByRole("button", { name: /live/i }));
    expect(p.onToggle).toHaveBeenCalled();
    expect(p.onSpeed).toHaveBeenCalledWith(60);
    expect(p.onLoad).toHaveBeenCalled();
    expect(p.onClose).toHaveBeenCalled();
  });
  it("shows progress while loading history", () => {
    setup({ loading: { done: 3, total: 12 } });
    expect(screen.getByRole("button", { name: /loading 3\/12/i })).toBeTruthy();
  });
});
