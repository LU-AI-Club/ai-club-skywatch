// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { DEFAULT_LAYERS, LayerSwitch } from "../../map/LayerSwitch";

afterEach(cleanup);

describe("<LayerSwitch>", () => {
  it("opens a grouped menu with context layers off by default", () => {
    render(<LayerSwitch layers={DEFAULT_LAYERS} onChange={() => {}} isFull={false} onFullscreen={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /layers/i }));
    for (const group of ["Traffic", "Chart", "Context"]) expect(screen.getByText(group)).toBeTruthy();
    expect((screen.getByLabelText(/weather radar/i) as HTMLInputElement).checked).toBe(false);
  });
  it("switches a layer and the data-tag mode", () => {
    const onChange = vi.fn();
    render(<LayerSwitch layers={DEFAULT_LAYERS} onChange={onChange} isFull={false} onFullscreen={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /layers/i }));
    fireEvent.click(screen.getByLabelText(/weather radar/i));
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_LAYERS, weather: true });
    fireEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_LAYERS, tags: "all" });
  });
  it("counts the context layers that are on, and resets to calm defaults", () => {
    const onChange = vi.fn();
    render(<LayerSwitch layers={{ ...DEFAULT_LAYERS, weather: true, heatmap: true }} onChange={onChange} isFull={false} onFullscreen={() => {}} />);
    const btn = screen.getByRole("button", { name: /layers/i });
    expect(btn.textContent).toContain("2");
    fireEvent.click(btn);
    fireEvent.click(screen.getByRole("button", { name: /reset to calm defaults/i }));
    expect(onChange).toHaveBeenLastCalledWith(DEFAULT_LAYERS);
  });
});
