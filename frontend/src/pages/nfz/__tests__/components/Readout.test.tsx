// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { Readout } from "../../components/Readout";

afterEach(cleanup);

describe("<Readout>", () => {
  it("shows the label and value", () => {
    render(<Readout label="Active zones" value="3 / 16" />);
    expect(screen.getByText("Active zones")).toBeTruthy();
    expect(screen.getByText("3 / 16")).toBeTruthy();
  });
  it("shows a shimmer instead of a value while loading", () => {
    const { container } = render(<Readout label="Incursions" value={42} loading />);
    expect(screen.queryByText("42")).toBeNull();
    expect(container.querySelector(".nfz-skel")).toBeTruthy();
  });
  it("draws one sparkline bar per time slice, highlighting non-empty ones", () => {
    const { container } = render(<Readout label="Incursions" value={3} spark={[0, 1, 0, 2]} />);
    expect(container.querySelectorAll(".nfz-spark rect")).toHaveLength(4);
    expect(container.querySelectorAll(".nfz-spark rect.has")).toHaveLength(2);
  });
  it("turns red when there's an open incursion", () => {
    const { container } = render(<Readout label="Incursions" value={1} alert />);
    expect(container.firstElementChild?.className).toContain("is-alert");
  });
});
