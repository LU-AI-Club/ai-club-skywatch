// ──────────────────────────────────────────────────────────────────────────
// PROXIMITY TEAM — your case-map overlay.  **This file is yours.**
//
// It draws how ONE proximity detection looks on the focused case map. Right now
// it falls back to the shared starter (one aircraft's track + a detection ring).
// Replace that with a picture of YOUR finding.
//
// You get `props.row` plus these helpers:
//   • useLeafletMap()      — the raw Leaflet map (../../../map/mapContext)
//   • useCaseLayer()       — an auto-cleaning layer group (../hooks)
//   • useAircraftTrack(id) — one aircraft's recent track (../hooks)
//
// Ideas for proximity: this case is about a PAIR — `row.member_entity_ids` holds
// both aircraft. Fetch BOTH tracks (call useAircraftTrack twice), draw both,
// draw a line between them at closest approach, and label it with
// `row.predicted_horizontal_nm` / `row.predicted_vertical_ft` / `row.t_cpa_seconds`.
// ──────────────────────────────────────────────────────────────────────────
import type { CaseOverlayProps } from "../../caseTypes";
import { DefaultCaseOverlay } from "../DefaultCaseOverlay";

export function ProximityCaseOverlay(props: CaseOverlayProps) {
  // TODO(proximity): replace this with your own layers (draw both aircraft).
  return <DefaultCaseOverlay {...props} />;
}
