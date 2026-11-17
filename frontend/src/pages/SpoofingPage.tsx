// SPOOFING TEAM — this page is yours. Design it however you like; you are not
// bound by the shared look used on the landing page and map. What is here is a
// working starting point you can keep, extend, or delete.
//
// Where to work:
//   - Data:   useSpoofingDetections(params) returns your rows exactly as stored
//             (your table's columns — the shape is yours to define).
//   - Map:    render <MapView> (import from ../map/MapView) and use
//             useLeafletMap() inside it to draw on the raw Leaflet map.
//   - Styling: the shared tokens live in theme.css, but you may bring your own.
import { useSpoofingDetections } from "../api/hooks";
import { DetectionTable } from "../components/DetectionTable";
import { EmptyState } from "../components/EmptyState";
import SpoofingSummary from "../components/SpoofingSummary";

export function SpoofingPage() {
  const { data, loading, error, reload } = useSpoofingDetections({ since_hours: 24 });
  const rows = data ?? [];

  return (
    <div className="page">
      <div className="page-head">
        <h1>Spoofing</h1>
        <p className="owner">
          Owned by the Spoofing team — design this page however you like. This is a
          starting point.
        </p>
      </div>

      {error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}

      <SpoofingSummary detections={rows} windowHours={24} />

      <div style={{ margin: "10px 0 16px" }}>
        <button className="btn ghost" onClick={reload} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <DetectionTable detections={rows} />
    </div>
  );
}