// The map key (bottom-left). Click its title to fold it away; the choice is
// remembered in this browser.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { ALTITUDE_BANDS } from "../altitude";
import { TRAIL_MINUTES } from "../trails";
import { PLANE_PATH } from "./TrafficLayer";

const STORAGE_KEY = "skywatch.nfz.legend";
function remembered(fallback: boolean): boolean {
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    return v == null ? fallback : v === "closed";
  } catch {
    return fallback;
  }
}
function remember(closed: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEY, closed ? "closed" : "open");
  } catch {
    /* not remembered */
  }
}

export function MapLegend({
  traffic,
  zones = true,
  chart = false,
  startClosed = false,
}: {
  traffic: "lines" | "planes";
  zones?: boolean;
  chart?: boolean;
  startClosed?: boolean;
}) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const legend = new L.Control({ position: "bottomleft" });
    legend.onAdd = () => {
      const div = L.DomUtil.create("div", `nfz-legend${remembered(startClosed) ? " is-closed" : ""}`);
      const ramp = ALTITUDE_BANDS.map((b) => `<span><i style="background:${b.color}"></i>${b.label}</span>`).join("");
      const trafficRows =
        traffic === "planes"
          ? `<div><svg class="nfz-lg-plane" viewBox="0 0 24 24"><path d="${PLANE_PATH}"/></svg>Aircraft, pointing where it's flying</div>
             <div><i class="nfz-ln nfz-ln--trail"></i>Where it's been (${TRAIL_MINUTES} min)</div>
             <div><span class="nfz-lg-arrows">↑↓</span>Climbing / descending (in data tags)</div>
             <div><i class="nfz-lg-lock"></i>Flagged by a detector recently</div>
             <div><i class="nfz-lg-emerg"></i>Emergency squawk (7500 / 7600 / 7700)</div>`
          : `<div><i class="nfz-ln nfz-ln--trail"></i>Where it's been (${TRAIL_MINUTES} min)</div>
             <div><i class="nfz-ln nfz-ln--head"></i>Direction of travel</div>`;
      div.innerHTML = `
        <div class="nfz-legend-title" role="button" tabindex="0" title="Click to show or hide${traffic === "planes" ? " · click a plane for its flight strip, hover to spotlight, zoom in for data tags" : ""}">Map key</div>
        ${zones ? `<div><i class="nfz-sw nfz-sw--restricted"></i>Prohibited / restricted</div><div><i class="nfz-sw nfz-sw--moa"></i>Military operations area</div>` : ""}
        ${trafficRows}
        <div class="nfz-lg-alt">Altitude ${ramp}</div>
        ${zones ? `<div><i class="nfz-lg-hit"></i>Where an incursion happened</div>` : ""}
        ${chart ? `<div><i class="nfz-ln nfz-ln--ring"></i>Range rings, 10 nm from KLYH</div>` : ""}
        ${traffic === "planes" ? `<div class="nfz-lg-hint">Click a plane for its flight strip</div>` : ""}`;
      L.DomEvent.disableClickPropagation(div);
      L.DomEvent.disableScrollPropagation(div);
      const title = div.querySelector<HTMLElement>(".nfz-legend-title");
      const flip = () => remember(div.classList.toggle("is-closed"));
      title?.addEventListener("click", flip);
      title?.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), flip()));
      return div;
    };
    legend.addTo(map);
    return () => {
      legend.remove();
    };
  }, [map, traffic, zones, chart, startClosed]);
  return null;
}
