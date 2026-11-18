// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { HotkeyHelp } from "../../components/HotkeyHelp";

afterEach(cleanup);

describe("<HotkeyHelp>", () => {
  it("lists the shortcuts, including sky replay", () => {
    render(<HotkeyHelp onClose={() => {}} />);
    expect(screen.getByRole("dialog", { name: /keyboard shortcuts/i })).toBeTruthy();
    for (const key of ["J / K", "Esc", "F", "R", "/", "?"]) expect(screen.getByText(key)).toBeTruthy();
  });
  it("closes from the button or by clicking outside", () => {
    const onClose = vi.fn();
    const { container } = render(<HotkeyHelp onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /close/i }));
    fireEvent.click(container.querySelector(".nfz-modal-backdrop")!);
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});
