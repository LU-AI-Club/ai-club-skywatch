// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Timeline } from "../../components/Timeline";
import { det } from "./fixtures";

afterEach(cleanup);

describe("<Timeline>", () => {
  it("draws one mark per incursion and opens it on click", () => {
    const onSelect = vi.fn();
    render(<Timeline rows={[det("a", 60), det("b", 120)]} hours={24} selectedId={null} onSelect={onSelect} />);
    const marks = screen.getAllByRole("button");
    expect(marks).toHaveLength(2);
    fireEvent.click(marks[0]);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ detection_id: "a" }));
  });
  it("says so when the window is empty, and labels the end NOW", () => {
    render(<Timeline rows={[]} hours={24} selectedId={null} onSelect={() => {}} />);
    expect(screen.getByText(/no incursions in this window/i)).toBeTruthy();
    expect(screen.getByText("NOW")).toBeTruthy();
  });
  it("highlights the selected incursion", () => {
    render(<Timeline rows={[det("a", 60)]} hours={24} selectedId="a" onSelect={() => {}} />);
    expect(screen.getByRole("button").className).toContain("is-selected");
  });
});
