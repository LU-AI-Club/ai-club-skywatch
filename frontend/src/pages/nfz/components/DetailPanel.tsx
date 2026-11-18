// One incursion in full: the detector's own explanation, a replay of the
// aircraft's track through the zone with its altitude profile, the facts,
// and the raw evidence/metadata.
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Link } from "react-router-dom";
import type { Detection } from "../../../api/types";
import { MapView } from "../../../map/MapView";
import { SeverityBadge } from "../../../components/SeverityBadge";
import { NoFlyZoneOverlay } from "../../overlays/NoFlyZoneOverlay";
import { ReplayLayer } from "../map/ReplayLayer";
import { ScrollGuard } from "../map/MapBehavior";
import { useTrack } from "../hooks/useTrack";
import { useReplay } from "../hooks/useReplay";
import { useHotkeys } from "../hooks/useHotkeys";
import { sampleTrack } from "../track";
import { duration, zuluTime } from "../format";
import { summaryOf } from "../csv";
import type { ZoneInfo } from "../zones";
import { AltitudeProfile } from "./AltitudeProfile";
import { ReplayControls } from "./ReplayControls";

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  if (typeof value === "object" && Object.keys(value as object).length === 0) return null;
  return (
    <details className="nfz-json">
      <summary className="nfz-label">{label}</summary>
      {typeof value === "string" ? (
        <div className="nfz-notam-text">{value}</div>
      ) : (
        <pre className="nfz-pre">{JSON.stringify(value, null, 2)}</pre>
      )}
    </details>
  );
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function DetailPanel({
  detection: d,
  zone,
  onClose,
  onShowOnMap,
  style,
}: {
  detection: Detection;
  zone?: ZoneInfo;
  onClose: () => void;
  onShowOnMap: () => void;
  style?: CSSProperties;
}) {
  const summary = summaryOf(d);
  const { points, loading, error } = useTrack(d);
  const entry = Date.parse(String(d.temporal_bounds_start));
  const exit = d.temporal_bounds_end ? Date.parse(String(d.temporal_bounds_end)) : null;
  const start = points[0]?.t ?? (Number.isFinite(entry) ? entry : Date.now());
  const end = points[points.length - 1]?.t ?? start + 1;
  const replay = useReplay(start, end, Number.isFinite(entry) ? entry - 60_000 : start);
  const sample = useMemo(() => sampleTrack(points, replay.t), [points, replay.t]);
  const inside = Number.isFinite(entry) && replay.t >= entry && replay.t <= (exit ?? end);
  const [copied, setCopied] = useState<"" | "ok" | "fail">("");
  useEffect(() => setCopied(""), [d.detection_id]);

  useHotkeys({ " ": () => points.length >= 2 && replay.toggle() });

  const fallback = useMemo(
    () => (typeof d.latitude === "number" && typeof d.longitude === "number" ? { lat: d.latitude, lon: d.longitude } : null),
    [d.latitude, d.longitude],
  );

  const facts: [string, string][] = [
    ["Aircraft", d.entity_id],
    ["Zone", `${String(d.zone_name ?? d.zone_id ?? "—")}`],
    ["Zone ID / type", `${String(d.zone_id ?? "—")} · ${String(d.zone_type ?? "—")}`],
    ["Time inside", duration(d.duration_seconds)],
    ["Entered", zuluTime(d.temporal_bounds_start)],
    ["Left", d.temporal_bounds_end ? zuluTime(d.temporal_bounds_end) : "still inside / open"],
    ["Last detected", zuluTime(d.last_detected_at)],
    ["Confidence", typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—"],
  ];

  return (
    <aside className="card nfz-panel" style={style} aria-label={`Incursion by ${d.entity_id}`}>
      <div className="nfz-panel-head">
        <div className="nfz-panel-id">
          <SeverityBadge severity={d.severity} />
          <strong>{d.entity_id}</strong>
        </div>
        <button className="btn ghost" onClick={onClose} title="Close (Esc)">
          Close
        </button>
      </div>
      <div className="nfz-panel-actions">
        <button
          className="nfz-chip"
          onClick={async () => setCopied((await copyText(window.location.href)) ? "ok" : "fail")}
          title="Copy a link that opens this incursion"
        >
          {copied === "ok" ? "Link copied ✓" : copied === "fail" ? "Copy failed: use the address bar" : "Copy link"}
        </button>
        {fallback && (
          <button className="nfz-chip" onClick={onShowOnMap}>
            Show on map above
          </button>
        )}
        <Link
          className="nfz-chip"
          to={`/map?ac=${encodeURIComponent(d.entity_id.replace(/^icao24:/, ""))}&d=${encodeURIComponent(d.detection_id)}`}
          title="Open the shared map, following this aircraft live"
        >
          Follow live on main map →
        </Link>
      </div>

      {summary && <p className="nfz-notam-text" style={{ marginTop: 12 }}>{summary}</p>}

      <div className="nfz-label" style={{ marginTop: 14 }}>
        Replay
      </div>
      <div className="nfz-minimap nfz-chartmap">
        <MapView showAircraft={false} style={{ height: "100%" }}>
          <NoFlyZoneOverlay detections={[d]} selectedId={d.detection_id} traffic="none" focusZoneId={String(d.zone_id ?? "")} />
          <ReplayLayer points={points} t={replay.t} entry={Number.isFinite(entry) ? entry : null} exit={exit} fallback={fallback} />
          <ScrollGuard />
        </MapView>
      </div>
      {loading ? (
        <div className="nfz-skel nfz-skel--bar" style={{ marginTop: 8 }} />
      ) : points.length >= 2 ? (
        <>
          <ReplayControls
            start={start}
            end={end}
            t={replay.t}
            playing={replay.playing}
            speed={replay.speed}
            sample={sample}
            inside={inside}
            onToggle={replay.toggle}
            onSeek={replay.seek}
            onSpeed={replay.setSpeed}
          />
          <div className="nfz-label" style={{ marginTop: 14 }}>
            Altitude profile
          </div>
          <AltitudeProfile
            points={points}
            t={replay.t}
            onSeek={replay.seek}
            entry={Number.isFinite(entry) ? entry : null}
            exit={exit}
            zone={zone}
          />
        </>
      ) : (
        <p className="nfz-hint">
          {error
            ? `Couldn't load this aircraft's track (${error}).`
            : "No recorded track around this incursion, so there is nothing to replay. The diamond marks where it was detected."}
        </p>
      )}

      <dl className="nfz-facts">
        {facts.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>

      <JsonBlock label="Evidence" value={d.evidence} />
      <JsonBlock label="Metadata" value={d.metadata} />
      <JsonBlock label="Geospatial context" value={d.geospatial_context} />
      <JsonBlock label="Tags" value={d.tags} />
    </aside>
  );
}
