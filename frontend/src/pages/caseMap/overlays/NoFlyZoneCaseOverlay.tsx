// ──────────────────────────────────────────────────────────────────────────
// NO-FLY-ZONE TEAM — your case-map overlay.  **This file is yours.**
//
// It draws how ONE no-fly-zone incursion looks on the focused case map. Right
// now it falls back to the shared starter (track + detection ring). Replace that
// with a picture of YOUR finding.
//
// You get `props.row` plus these helpers:
//   • useLeafletMap()      — the raw Leaflet map (../../../map/mapContext)
//   • useCaseLayer()       — an auto-cleaning layer group (../hooks)
//   • useAircraftTrack(id) — the aircraft's recent track (../hooks)
//
// Ideas for no-fly zone: draw the ZONE POLYGON this incursion is in and shade
// it, then draw the aircraft's track and highlight the part inside the zone.
// The zone geometry is NOT in the API — fetch it from the airspace GeoJSON you
// copied into public/airspace/ and match it by `row.zone_id` (see the team
// guide), then L.geoJSON(feature).addTo(layer).
// ──────────────────────────────────────────────────────────────────────────
import type { CaseOverlayProps } from "../../caseTypes";
import { DefaultCaseOverlay } from "../DefaultCaseOverlay";

export function NoFlyZoneCaseOverlay(props: CaseOverlayProps) {
  // TODO(no-fly-zone): replace this with your own layers (draw the zone polygon).
  return <DefaultCaseOverlay {...props} />;
}
