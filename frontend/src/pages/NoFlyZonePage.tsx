// NO-FLY-ZONE TEAM page. Shows incursions into restricted airspace, whether the
// detector is alive, and a detail panel with the detector's own explanation plus
// the aircraft's track drawn against the zone it entered.
//
// Zone polygons come from public/airspace/ (copied from
// air/detectors/no_fly_zone/fixtures/airspace/), not the API.
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import * as L from "leaflet";
import { useDetectorRuns, useNoFlyZoneDetections } from "../api/hooks";
import { fetchJSON } from "../api/client";
import type { Detection, DetectorRun } from "../api/types";
import { MapView } from "../map/MapView";
import { useLeafletMap } from "../map/mapContext";
import { SeverityBadge } from "../components/SeverityBadge";
import { StatCard } from "../components/StatCard";
import { EmptyState } from "../components/EmptyState";
import { NoFlyZoneOverlay } from "./overlays/NoFlyZoneOverlay";

const DETECTOR_ID = "skywatch.no_fly_zone";
const RANGES = [
  { label: "1 hour", hours: 1 },
  { label: "6 hours", hours: 6 },
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 168 },
  { label: "30 days", hours: 720 },
];
const SEVERITIES = ["", "info", "low", "medium", "high", "critical"];

// ---------------------------------------------------------------- formatting

function ago(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.now() - new Date(iso).getTime();
  if (!Number.isFinite(ms)) return "—";
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} d ago`;
}

function duration(v: unknown): string {
  const s = Number(v);
  if (!Number.isFinite(s)) return "—";
  if (s < 60) return `${Math.round(s)} s`;
  const m = Math.floor(s / 60);
  return `${m} m ${Math.round(s % 60)} s`;
}

function localTime(iso: unknown): string {
  if (typeof iso !== "string") return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

// --------------------------------------------------------------- liveness

function DetectorStatus({ runs, error }: { runs: DetectorRun[] | null; error: string | null }) {
  const last = runs?.[0];
  let text: string;
  let color = "var(--muted)";
  if (error) {
    text = `Couldn't check detector status: ${error}`;
    color = "var(--sev-critical)";
  } else if (!runs) {
    text = "Checking detector status…";
  } else if (!last) {
    text = "No detector runs recorded — the detector may never have run.";
    color = "var(--sev-high)";
  } else {
    const found = last.counts?.detections ?? last.counts?.emitted ?? last.counts?.found;
    const status = last.status.toUpperCase();
    color =
      status === "SUCCESS"
        ? "var(--sev-low)"
        : status === "FAILED"
          ? "var(--sev-critical)"
          : "var(--sev-medium)";
    text =
      `Detector last ran ${ago(last.completed_at ?? last.started_at)} · ${status}` +
      (found !== undefined ? ` · found ${String(found)}` : "") +
      (last.error ? ` · ${last.error}` : "");
  }
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--muted)", fontSize: 14 }}>
      <span style={{ width: 9, height: 9, borderRadius: "50%", background: color, flex: "none" }} />
      {text}
    </div>
  );
}

// ------------------------------------------------------------- detail view

function TrackLayer({ detection }: { detection: Detection }) {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const layer = L.layerGroup().addTo(map);
    let cancelled = false;
    const hasPoint = typeof detection.latitude === "number" && typeof detection.longitude === "number";
    if (hasPoint) map.setView([detection.latitude!, detection.longitude!], 10);

    fetchJSON<{ geometry?: { coordinates?: [number, number][] } }>("/observations/tracks", {
      entity_id: detection.entity_id,
      lookback_hours: 24,
    })
      .then((track) => {
        if (cancelled) return;
        const coords = track.geometry?.coordinates ?? [];
        if (coords.length < 2) return;
        const line = L.polyline(
          coords.map(([lon, lat]) => [lat, lon] as [number, number]),
          { color: "#22d3ee", weight: 2, opacity: 0.9 },
        ).addTo(layer);
        if (!hasPoint) map.fitBounds(line.getBounds(), { padding: [20, 20] });
      })
      .catch(() => {
        /* no recent track — the incursion marker still shows */
      });
    return () => {
      cancelled = true;
      layer.remove();
    };
  }, [map, detection]);
  return null;
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined) return null;
  if (typeof value === "object" && Object.keys(value as object).length === 0) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div style={{ color: "var(--muted)", fontSize: 12, textTransform: "uppercase", marginBottom: 4 }}>
        {label}
      </div>
      {typeof value === "string" ? (
        <div>{value}</div>
      ) : (
        <pre style={preStyle}>{JSON.stringify(value, null, 2)}</pre>
      )}
    </div>
  );
}

// Pull the detector's own plain-language explanation, if it wrote one.
function summaryOf(d: Detection): string | null {
  const ev = d.evidence as Record<string, unknown> | string | null | undefined;
  if (typeof ev === "string") return ev;
  if (ev && typeof ev === "object") {
    for (const k of ["summary", "explanation", "reason", "message", "description"]) {
      if (typeof ev[k] === "string") return ev[k] as string;
    }
  }
  return null;
}

function DetailPanel({ detection, onClose }: { detection: Detection; onClose: () => void }) {
  const d = detection;
  const summary = summaryOf(d);
  const facts: [string, string][] = [
    ["Aircraft", d.entity_id],
    ["Zone", `${String(d.zone_name ?? d.zone_id ?? "—")}`],
    ["Zone ID / type", `${String(d.zone_id ?? "—")} · ${String(d.zone_type ?? "—")}`],
    ["Time inside", duration(d.duration_seconds)],
    ["Entered", localTime(d.temporal_bounds_start)],
    ["Left", d.temporal_bounds_end ? localTime(d.temporal_bounds_end) : "still inside / open"],
    ["Last detected", localTime(d.last_detected_at)],
    ["Confidence", typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—"],
  ];
  return (
    <aside className="card" style={panelStyle}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div style={{ display: "flex", gap: 8, alignItems: "center", minWidth: 0 }}>
          <SeverityBadge severity={d.severity} />
          <strong style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{d.entity_id}</strong>
        </div>
        <button className="btn ghost" onClick={onClose}>Close</button>
      </div>

      {summary && <p style={{ margin: "12px 0 0" }}>{summary}</p>}

      <div style={{ height: 260, marginTop: 12, borderRadius: "var(--radius)", overflow: "hidden" }}>
        <MapView showAircraft={false}>
          <NoFlyZoneOverlay detections={[d]} selectedId={d.detection_id} preferLive={false} />
          <TrackLayer detection={d} />
        </MapView>
      </div>
      <div style={{ color: "var(--muted)", fontSize: 12, marginTop: 4 }}>
        Cyan line: the aircraft's track over the last 24 h (if any). Red: zone entered.
      </div>

      <dl style={dlStyle}>
        {facts.map(([k, v]) => (
          <div key={k} style={{ display: "contents" }}>
            <dt style={{ color: "var(--muted)" }}>{k}</dt>
            <dd style={{ margin: 0 }}>{v}</dd>
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

// --------------------------------------------------------------------- page

export function NoFlyZonePage() {
  const [hours, setHours] = useState(24);
  const [severity, setSeverity] = useState("");
  const [search, setSearch] = useState("");
  const [zoneType, setZoneType] = useState("");
  const [selected, setSelected] = useState<Detection | null>(null);

  const { data, loading, error, reload } = useNoFlyZoneDetections({
    since_hours: hours,
    severity: severity || undefined,
  });
  const runs = useDetectorRuns({ detector_id: DETECTOR_ID, limit: 1 });

  // Keep both fresh while the page is open.
  const reloadRuns = runs.reload;
  useEffect(() => {
    const id = window.setInterval(() => {
      reload();
      reloadRuns();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [reload, reloadRuns]);

  const all = data ?? [];
  const zoneTypes = useMemo(
    () => [...new Set(all.map((d) => String(d.zone_type ?? "")).filter(Boolean))].sort(),
    [all],
  );
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return all.filter(
      (d) =>
        (!zoneType || d.zone_type === zoneType) &&
        (!q ||
          d.entity_id.toLowerCase().includes(q) ||
          String(d.zone_id ?? "").toLowerCase().includes(q) ||
          String(d.zone_name ?? "").toLowerCase().includes(q)),
    );
  }, [all, search, zoneType]);

  const stats = useMemo(() => {
    const zones = new Set(rows.map((d) => String(d.zone_id ?? "unknown")));
    const aircraft = new Set(rows.map((d) => d.entity_id));
    const open = rows.filter((d) => !d.temporal_bounds_end).length;
    const longest = rows.reduce((m, d) => Math.max(m, Number(d.duration_seconds) || 0), 0);
    return { zones: zones.size, aircraft: aircraft.size, open, longest };
  }, [rows]);

  const rangeLabel = RANGES.find((r) => r.hours === hours)?.label ?? `${hours} h`;
  const dash = (v: string | number) => (loading && !data ? "…" : v);

  return (
    <div className="page">
      <div className="page-head">
        <h1>No-fly zone</h1>
        <p className="owner">Aircraft that entered restricted, prohibited, or MOA airspace.</p>
      </div>

      <DetectorStatus runs={runs.data} error={runs.error} />

      {error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}

      <div className="stat-grid" style={{ marginTop: 14 }}>
        <StatCard label={`Incursions (${rangeLabel})`} value={dash(rows.length)} />
        <StatCard label="Zones involved" value={dash(stats.zones)} />
        <StatCard label="Aircraft involved" value={dash(stats.aircraft)} />
        <StatCard label="Longest time inside" value={dash(duration(stats.longest))} />
      </div>

      <div style={controlsStyle}>
        <label style={labelStyle}>
          Time range
          <select value={hours} onChange={(e) => setHours(Number(e.target.value))} style={inputStyle}>
            {RANGES.map((r) => (
              <option key={r.hours} value={r.hours}>Last {r.label}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          Severity
          <select value={severity} onChange={(e) => setSeverity(e.target.value)} style={inputStyle}>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>{s || "All"}</option>
            ))}
          </select>
        </label>
        <label style={labelStyle}>
          Zone type
          <select value={zoneType} onChange={(e) => setZoneType(e.target.value)} style={inputStyle}>
            <option value="">All</option>
            {zoneTypes.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
        </label>
        <label style={{ ...labelStyle, flex: "1 1 200px" }}>
          Search aircraft or zone
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="icao24:a1b2c3, P-56, DEMO-1…"
            style={inputStyle}
          />
        </label>
        <button className="btn ghost" onClick={reload} disabled={loading} style={{ alignSelf: "flex-end" }}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", flexWrap: "wrap" }}>
        <div style={{ flex: "1 1 520px", minWidth: 0, overflowX: "auto" }}>
          {rows.length === 0 && !loading ? (
            <EmptyState
              message={
                runs.data?.[0]?.status?.toUpperCase() === "SUCCESS"
                  ? "No incursions in this window — the detector is running, the sky is clear."
                  : "No incursions for the current filters."
              }
            />
          ) : (
            <table className="table">
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Aircraft</th>
                  <th>Zone</th>
                  <th>Type</th>
                  <th>Time inside</th>
                  <th>Last detected</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((d) => (
                  <tr
                    key={d.detection_id}
                    onClick={() => setSelected(d)}
                    style={{
                      cursor: "pointer",
                      background:
                        selected?.detection_id === d.detection_id ? "var(--raised)" : undefined,
                    }}
                  >
                    <td><SeverityBadge severity={d.severity} /></td>
                    <td>{d.entity_id}</td>
                    <td title={String(d.zone_name ?? "")}>{String(d.zone_id ?? "—")}</td>
                    <td>{String(d.zone_type ?? "—")}</td>
                    <td>
                      {duration(d.duration_seconds)}
                      {!d.temporal_bounds_end && (
                        <span style={{ color: "var(--sev-critical)", marginLeft: 6 }}>● open</span>
                      )}
                    </td>
                    <td title={localTime(d.last_detected_at)}>{ago(d.last_detected_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {selected && <DetailPanel detection={selected} onClose={() => setSelected(null)} />}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------- styles

const controlsStyle: CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 12,
  margin: "16px 0",
};
const labelStyle: CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 4,
  fontSize: 12,
  color: "var(--muted)",
};
const inputStyle: CSSProperties = {
  background: "var(--surface)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  padding: "7px 10px",
  fontSize: 14,
};
const panelStyle: CSSProperties = {
  flex: "1 1 380px",
  maxWidth: 520,
  minWidth: 0,
  position: "sticky",
  top: 16,
};
const dlStyle: CSSProperties = {
  display: "grid",
  gridTemplateColumns: "max-content 1fr",
  gap: "6px 14px",
  margin: "14px 0 0",
  fontSize: 14,
};
const preStyle: CSSProperties = {
  margin: 0,
  padding: 10,
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: "var(--radius)",
  fontSize: 12,
  overflowX: "auto",
  maxHeight: 260,
};
