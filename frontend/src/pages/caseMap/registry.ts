// Which overlay draws each detector's case map. The CaseMap looks a detection's
// detector up here; an unmapped one falls back to the shared DefaultCaseOverlay.
// Each team owns its entry's file under overlays/ — editing one never touches
// the others.
import type { ComponentType } from "react";
import type { CaseOverlayProps, DetectorKey } from "../caseTypes";
import { SpoofingCaseOverlay } from "./overlays/SpoofingCaseOverlay";
import { ProximityCaseOverlay } from "./overlays/ProximityCaseOverlay";
import { NoFlyZoneCaseOverlay } from "./overlays/NoFlyZoneCaseOverlay";

export const CASE_OVERLAYS: Record<DetectorKey, ComponentType<CaseOverlayProps>> = {
  spoofing: SpoofingCaseOverlay,
  proximity: ProximityCaseOverlay,
  "no-fly-zone": NoFlyZoneCaseOverlay,
};
