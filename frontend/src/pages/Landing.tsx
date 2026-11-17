import { Link } from "react-router-dom";
import { useObservations } from "../api/observations";

// Landing page: the club's semester work. Replace the copy below with the real
// writeup — it is intentionally a placeholder.
export function Landing() {
  const { aircraft, lastUpdated } = useObservations();
  return (
    <div className="page">
      <div className="page-head">
        <h1>AI Club SkyWatch</h1>
        <p className="owner">
          Live airspace monitoring over Lynchburg, built by the club. Three teams,
          three detectors, one map.
        </p>
      </div>

      <div className="card" style={{ marginBottom: 18 }}>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          This semester the club built a full pipeline: a live ADS-B feed lands in a
          database, three detectors watch it, and this app shows what they find.
          {"  "}
          <strong style={{ color: "var(--text)" }}>
            {aircraft.length} aircraft
          </strong>{" "}
          are being tracked right now
          {lastUpdated ? ` (updated ${lastUpdated.toLocaleTimeString()}).` : "."}
        </p>
        <p style={{ marginBottom: 0, color: "var(--muted)" }}>
          TODO: replace this with the semester-work writeup.
        </p>
      </div>

      <div className="stat-grid">
        <Link to="/map" className="card">
          <div className="value" style={{ fontSize: 18 }}>Live map →</div>
          <div className="label" style={{ color: "var(--muted)" }}>
            Every aircraft, with detector overlays.
          </div>
        </Link>
        <Link to="/spoofing" className="card">
          <div className="value" style={{ fontSize: 18 }}>Spoofing →</div>
          <div className="label" style={{ color: "var(--muted)" }}>
            Identity and physics anomalies.
          </div>
        </Link>
        <Link to="/proximity" className="card">
          <div className="value" style={{ fontSize: 18 }}>Proximity →</div>
          <div className="label" style={{ color: "var(--muted)" }}>
            Aircraft on a close approach.
          </div>
        </Link>
        <Link to="/no-fly-zone" className="card">
          <div className="value" style={{ fontSize: 18 }}>No-fly zone →</div>
          <div className="label" style={{ color: "var(--muted)" }}>
            Incursions into restricted airspace.
          </div>
        </Link>
      </div>
    </div>
  );
}
