// Shared types for the detections console and its per-case map overlays.
// Kept in their own module so a team's overlay file can import them without
// pulling in the whole CasesPage.
import type { Detection } from "../api/types";

export type DetectorKey = "spoofing" | "proximity" | "no-fly-zone";

export const DETECTOR_LABEL: Record<DetectorKey, string> = {
  spoofing: "Spoofing",
  proximity: "Proximity",
  "no-fly-zone": "No-fly zone",
};

// A detection tagged with which detector it came from, so the merged queue and
// the map can tell the three apart.
export interface CaseRow extends Detection {
  _detector: DetectorKey;
}

// Every case-map overlay — the shared default and each team's — is a component
// with this one prop. It draws onto the map imperatively (see the helpers in
// caseMap/hooks.ts) and returns null.
export interface CaseOverlayProps {
  row: CaseRow;
}
