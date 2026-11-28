// ──────────────────────────────────────────────────────────────────────────
// SPOOFING TEAM — your case-map overlay.  **This file is yours.**
//
// It draws how ONE spoofing detection looks on the focused case map (the small
// map inside each detection's case on the /cases page). Right now it falls back
// to the shared starter (track + detection ring). Replace that with a picture of
// YOUR finding.
//
// You get:
//   • `props.row` — the full detection row (severity, evidence, metadata, your
//     columns, entity_id, latitude/longitude …).
//   • `useLeafletMap()`      — the raw Leaflet map (import from ../../../map/mapContext)
//   • `useCaseLayer()`       — a layer group that auto-cleans up (import from ../hooks)
//   • `useAircraftTrack(id)` — the aircraft's recent track as [lat,lon] pairs (../hooks)
//
// Ideas for spoofing: highlight the flagged aircraft, and draw the anomalous
// segment of its track in red (e.g. the teleport jump, or the stretch where the
// reported speed/vertical rate disagreed), with a marker on the offending fix.
// Read the gate and measured values out of row.metadata / row.evidence.
// ──────────────────────────────────────────────────────────────────────────
import type { CaseOverlayProps } from "../../caseTypes";
import { DefaultCaseOverlay } from "../DefaultCaseOverlay";

export function SpoofingCaseOverlay(props: CaseOverlayProps) {
  // TODO(spoofing): replace this with your own layers.
  return <DefaultCaseOverlay {...props} />;
}
