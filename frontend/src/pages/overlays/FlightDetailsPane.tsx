// frontend/src/pages/overlays/FlightDetailsPane.tsx
import { useObservations } from "../../api/observations";
import { useSpoofingDetections } from "../../api/hooks";
import { entityIdOf } from "./AircraftSelectLayer";

const num = (v: number | null | undefined, suffix: string) =>
  typeof v === "number" && Number.isFinite(v) ? `${v.toFixed(1)}${suffix}` : "—";

export function FlightDetailsPane({
  entityId,
  onClose,
}: {
  entityId: string;
  onClose: () => void;
}) {
  const { aircraft } = useObservations();
  const live = aircraft.find((f) => entityIdOf(f.properties.icao24) === entityId)?.properties;

  const { data: detections, loading } = useSpoofingDetections({
    entity_id: entityId,
    since_hours: 24,
  });

  return (
    <aside
      style={{
        position: "absolute", top: 0, right: 0, bottom: 0, width: 320,
        zIndex: 1000, overflowY: "auto", padding: 16,
        background: "var(--surface, #14141a)", color: "var(--text, #e5e5ea)",
        borderLeft: "1px solid var(--border, #2a2a33)",
      }}
    >
      <button onClick={onClose} style={{ float: "right" }} aria-label="Close">×</button>
      <h2 style={{ margin: 0 }}>{live?.callsign || live?.icao24 || entityId}</h2>

      {live ? (
        <dl style={{ lineHeight: 1.7 }}>
          <dt>ICAO24</dt><dd>{live.icao24}</dd>
          <dt>Altitude</dt><dd>{String(live.altitude ?? "—")}</dd>
          <dt>Speed</dt><dd>{num(live.sog, " kn")}</dd>
          <dt>Track</dt><dd>{num(live.cog, "°")}</dd>
          <dt>Position age</dt><dd>{num(live.position_age_hours, " h")}</dd>
        </dl>
      ) : (
        <p>This aircraft is no longer in the live window.</p>
      )}

      <h3>Spoofing detections (24h)</h3>
      {loading && <p>Loading…</p>}
      {!loading && !detections?.length && <p>None for this aircraft.</p>}
      {detections?.map((d) => {
        const facts = (d.metadata as any)?.explanation_facts as string[] | undefined;
        return (
          <div key={d.detection_id} style={{ marginBottom: 12 }}>
            <strong>{d.severity}</strong>
            <ul>{facts?.map((f) => <li key={f}>{f}</li>)}</ul>
          </div>
        );
      })}
    </aside>
  );
}