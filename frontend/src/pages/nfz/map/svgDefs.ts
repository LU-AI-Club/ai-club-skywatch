// Diagonal hatch patterns used to fill the zones, like a sectional chart.
// They live in one hidden <svg> in the page; Leaflet's zone shapes point at
// them from CSS with `fill: url(#nfz-hatch-…)`.
import { CHART_BLUE, CHART_MAGENTA } from "../zones";

const DEFS_ID = "nfz-svg-defs";

function pattern(id: string, color: string, angle: number, line: number, wash: number): string {
  return (
    `<pattern id="${id}" patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(${angle})">` +
    `<rect width="7" height="7" fill="${color}" fill-opacity="${wash}"/>` +
    `<line x1="0" y1="0" x2="0" y2="7" stroke="${color}" stroke-width="1.4" stroke-opacity="${line}"/>` +
    `</pattern>`
  );
}

export function ensureHatchDefs(): void {
  if (typeof document === "undefined" || document.getElementById(DEFS_ID)) return;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("id", DEFS_ID);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("width", "0");
  svg.setAttribute("height", "0");
  svg.style.position = "absolute";
  svg.style.width = "0";
  svg.style.height = "0";
  svg.style.overflow = "hidden";
  svg.innerHTML =
    "<defs>" +
    pattern("nfz-hatch-moa", CHART_MAGENTA, 45, 0.2, 0.03) +
    pattern("nfz-hatch-moa-hot", CHART_MAGENTA, 45, 0.45, 0.1) +
    pattern("nfz-hatch-restricted", CHART_BLUE, -45, 0.28, 0.05) +
    pattern("nfz-hatch-restricted-hot", CHART_BLUE, -45, 0.55, 0.14) +
    "</defs>";
  document.body.appendChild(svg);
}
