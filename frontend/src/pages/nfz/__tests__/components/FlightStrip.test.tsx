// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ObservationsProvider } from "../../../../api/observations";
import { FlightStrip } from "../../components/FlightStrip";
import { NOW, det, plane } from "./fixtures";

// The shared aircraft feed polls the API; give it an empty answer.
beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ type: "FeatureCollection", features: [] }) })));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const wrap = (ui: ReactNode) =>
  render(
    <MemoryRouter>
      <ObservationsProvider>{ui}</ObservationsProvider>
    </MemoryRouter>,
  );

const base = { detections: [], follow: false, onFollow: () => {}, onClose: () => {} };

describe("<FlightStrip>", () => {
  it("shows the aircraft's callsign, codes and numbers", () => {
    wrap(<FlightStrip {...base} id="a1b2c3" aircraft={[plane("a1b2c3")]} />);
    expect(screen.getByText("DAL1729")).toBeTruthy();
    expect(screen.getByText(/SQK 1200/)).toBeTruthy();
    expect(screen.getByText("9,000 ft")).toBeTruthy();
    expect(screen.getByText("230 kt")).toBeTruthy();
    expect(screen.getByText(/KLYH \d{3}°/)).toBeTruthy();
  });
  it("flags emergency squawks", () => {
    wrap(<FlightStrip {...base} id="a1b2c3" aircraft={[plane("a1b2c3", { squawk: "7700" })]} />);
    expect(screen.getByText(/SQUAWK 7700 · EMERGENCY/)).toBeTruthy();
  });
  it("lists recent detections with a replay link for no-fly-zone ones", () => {
    wrap(<FlightStrip {...base} id="a1b2c3" aircraft={[plane("a1b2c3")]} detections={[det("d1", 5)]} />);
    expect(screen.getByRole("link", { name: /replay/i }).getAttribute("href")).toBe("/no-fly-zone?d=d1");
  });
  it("toggles follow and closes", () => {
    const onFollow = vi.fn();
    const onClose = vi.fn();
    wrap(<FlightStrip {...base} id="a1b2c3" aircraft={[plane("a1b2c3")]} onFollow={onFollow} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /follow/i }));
    fireEvent.click(screen.getByRole("button", { name: /close flight strip/i }));
    expect(onFollow).toHaveBeenCalledWith(true);
    expect(onClose).toHaveBeenCalled();
  });
  it("says when it's showing a replay moment, or when the aircraft isn't in the feed", () => {
    wrap(<FlightStrip {...base} id="a1b2c3" aircraft={[plane("a1b2c3")]} replayAt={NOW - 60_000} />);
    expect(screen.getByText(/Replay · as of/)).toBeTruthy();
    cleanup();
    wrap(<FlightStrip {...base} id="ffffff" aircraft={[]} />);
    expect(screen.getByText(/not in the live feed/i)).toBeTruthy();
  });
});
