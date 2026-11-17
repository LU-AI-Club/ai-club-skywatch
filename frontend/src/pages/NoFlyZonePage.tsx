// NO-FLY-ZONE TEAM page: a live airspace-incursion console.
//
//   - Map: the 16 zones the live detector loads (public/airspace/*.geojson),
//     colored by type, plus one marker per incursion episode. Dashed outline =
//     part-time (scheduled / NOTAM) zone; solid = always active.
//   - Filters: time window, severity, zone type, ongoing-only.
//   - Side panel: the selected incursion's explanation, or the selected zone's
//     details, or a ranked list of zones by incursion count.
//   - Table: every incursion in the window; click a row to fly to it.
//
// Data refreshes on the app-wide interval (config.refreshIntervalMs).
// Helpers live in ./nfz/; styles in ./nfz/nfz.css (scoped under .nfz).
import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import * as L from "leaflet";
import { config } from "../config";
import { useNoFlyZoneDetections } from "../api/hooks";
import type { Detection } from "../api/types";
import { MapView } from "../map/MapView";
import { SeverityBadge } from "../components/SeverityBadge";
import { EmptyState } from "../components/EmptyState";
import { FlyTo, IncursionLayer, ZoneLayer } from "./nfz/NfzMapLayers";
// MapLibre is ~800 kB, so the 3D view loads only when it's first opened.
const Nfz3DMap = lazy(() => import("./nfz/Nfz3DMap").then((m) => ({ default: m.Nfz3DMap })));
import {
  ZONE_TYPES,
  durationSeconds,
  fmtAgo,
  fmtAltBand,
  fmtDuration,
  isOngoing,
  meta,
  useAirspace,
  zoneColor,
  zoneIdOf,
  zoneNameOf,
  zoneTypeOf,
  type ZoneFeature,
} from "./nfz/zones";
import "./nfz/nfz.css";

const WINDOWS = [
  { hours: 1, label: "1h" },
  { hours: 6, label: "6h" },
  { hours: 24, label: "24h" },
  { hours: 72, label: "3d" },
  { hours: 168, label: "7d" },
];

const SEVERITIES = ["critical", "high", "medium", "low", "info"];
const SEV_RANK: Record<string, number> = Object.fromEntries(
  SEVERITIES.map((s, i) => [s, SEVERITIES.length - i]),
);
const sevRank = (d: Detection) => SEV_RANK[String(d.severity).toLowerCase()] ?? 0;

function toggle<T>(set: Set<T>, value: T): Set<T> {
  const next = new Set(set);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

export function NoFlyZonePage() {
  const [windowHours, setWindowHours] = useState(24);
  const [severities, setSeverities] = useState<Set<string>>(new Set());
  const [zoneTypes, setZoneTypes] = useState<Set<string>>(new Set());
  const [ongoingOnly, setOngoingOnly] = useState(false);
  const [showAircraft, setShowAircraft] = useState(true);
  const [view, setView] = useState<"2d" | "3d">("3d");
  const [selectedZone, setSelectedZone] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [flyTarget, setFlyTarget] = useState<L.LatLngExpression | L.LatLngBounds | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [now, setNow] = useState(Date.now());

  const { data, loading, error, reload } = useNoFlyZoneDetections({
    since_hours: windowHours,
    limit: 2000,
  });
  const { zones, error: zoneError } = useAirspace();

  // Live refresh on the shared interval; also ticks "now" for ongoing durations.
  useEffect(() => {
    const id = window.setInterval(() => {
      reload();
      setNow(Date.now());
    }, config.refreshIntervalMs);
    return () => window.clearInterval(id);
  }, [reload]);
  useEffect(() => {
    if (data) setLastUpdated(new Date());
  }, [data]);

  const all = data ?? [];

  // Everything except the zone selection — zone counts on the map/list use this
  // so picking a zone doesn't zero out every other zone.
  const filtered = useMemo(
    () =>
      all.filter(
        (d) =>
          (!severities.size || severities.has(String(d.severity).toLowerCase())) &&
          (!zoneTypes.size || zoneTypes.has(zoneTypeOf(d))) &&
          (!ongoingOnly || isOngoing(d)),
      ),
    [all, severities, zoneTypes, ongoingOnly],
  );

  const visible = useMemo(
    () =>
      (selectedZone ? filtered.filter((d) => zoneIdOf(d) === selectedZone) : filtered)
        .slice()
        .sort(
          (a, b) =>
            Number(isOngoing(b)) - Number(isOngoing(a)) ||
            sevRank(b) - sevRank(a) ||
            Date.parse(b.last_detected_at) - Date.parse(a.last_detected_at),
        ),
    [filtered, selectedZone],
  );

  const hitCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const d of filtered) m.set(zoneIdOf(d), (m.get(zoneIdOf(d)) ?? 0) + 1);
    return m;
  }, [filtered]);

  const stats = useMemo(() => {
    const longest = Math.max(0, ...visible.map((d) => durationSeconds(d, now) ?? 0));
    return {
      ongoing: visible.filter(isOngoing).length,
      total: visible.length,
      aircraft: new Set(visible.map((d) => d.entity_id)).size,
      zones: new Set(visible.map(zoneIdOf)).size,
      severe: visible.filter((d) => sevRank(d) >= SEV_RANK.high).length,
      longest,
    };
  }, [visible, now]);

  const zoneById = useMemo(
    () => new Map(zones.map((z) => [z.properties.zone_id, z])),
    [zones],
  );
  const selected = visible.find((d) => d.detection_id === selectedId) ?? null;

  const selectZone = (zoneId: string | null) => {
    setSelectedZone(zoneId);
    setSelectedId(null);
    const z = zoneId ? zoneById.get(zoneId) : null;
    if (z) setFlyTarget(L.geoJSON(z as unknown as GeoJSON.Feature).getBounds());
  };

  const selectIncursion = (id: string) => {
    setSelectedId(id);
    const d = all.find((x) => x.detection_id === id);
    if (d && typeof d.latitude === "number" && typeof d.longitude === "number") {
      setFlyTarget([d.latitude, d.longitude]);
    }
  };

  const clearFilters = () => {
    setSeverities(new Set());
    setZoneTypes(new Set());
    setOngoingOnly(false);
    setSelectedZone(null);
    setSelectedId(null);
  };
  const anyFilter =
    severities.size > 0 || zoneTypes.size > 0 || ongoingOnly || selectedZone !== null;

  return (
    <div className="nfz">
      <header className="nfz-head">
        <div>
          <h1>No-fly zone monitor</h1>
          <p className="nfz-sub">
            Aircraft entering prohibited, restricted and special-use airspace around KLYH
          </p>
        </div>
        <div className="nfz-live">
          <span className={`nfz-dot ${error ? "bad" : ""}`} />
          {error ? "Offline" : lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Loading…"}
          <button className="btn ghost" onClick={reload} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </header>

      {error && <EmptyState kind="error" message={`Couldn't load incursions: ${error}`} />}
      {zoneError && (
        <EmptyState kind="error" message={`Couldn't load airspace polygons: ${zoneError}`} />
      )}

      <section className="nfz-kpis">
        <Kpi label="Ongoing now" value={stats.ongoing} alert={stats.ongoing > 0} />
        <Kpi label="Incursions" value={stats.total} />
        <Kpi label="Aircraft" value={stats.aircraft} />
        <Kpi label="Zones breached" value={stats.zones} />
        <Kpi label="High / critical" value={stats.severe} alert={stats.severe > 0} />
        <Kpi label="Longest dwell" value={fmtDuration(stats.longest || null)} />
      </section>

      <section className="nfz-filters">
        <div className="nfz-seg" role="group" aria-label="Map view">
          <button className={view === "2d" ? "on" : ""} onClick={() => setView("2d")}>
            2D map
          </button>
          <button className={view === "3d" ? "on" : ""} onClick={() => setView("3d")}>
            3D airspace
          </button>
        </div>
        <div className="nfz-seg" role="group" aria-label="Time window">
          {WINDOWS.map((w) => (
            <button
              key={w.hours}
              className={windowHours === w.hours ? "on" : ""}
              onClick={() => setWindowHours(w.hours)}
            >
              {w.label}
            </button>
          ))}
        </div>

        <div className="nfz-chips" aria-label="Severity">
          {SEVERITIES.map((s) => (
            <button
              key={s}
              className={`nfz-chip ${severities.has(s) ? "on" : ""}`}
              style={{ ["--chip" as string]: `var(--sev-${s})` }}
              onClick={() => setSeverities((cur) => toggle(cur, s))}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="nfz-chips" aria-label="Zone type">
          {ZONE_TYPES.map((z) => (
            <button
              key={z.type}
              className={`nfz-chip ${zoneTypes.has(z.type) ? "on" : ""}`}
              style={{ ["--chip" as string]: z.color }}
              onClick={() => setZoneTypes((cur) => toggle(cur, z.type))}
            >
              {z.label}
            </button>
          ))}
        </div>

        <label className="nfz-check">
          <input
            type="checkbox"
            checked={ongoingOnly}
            onChange={(e) => setOngoingOnly(e.target.checked)}
          />
          Ongoing only
        </label>
        <label className="nfz-check">
          <input
            type="checkbox"
            checked={showAircraft}
            onChange={(e) => setShowAircraft(e.target.checked)}
          />
          Live aircraft
        </label>
        {anyFilter && (
          <button className="nfz-link" onClick={clearFilters}>
            Clear filters
          </button>
        )}
      </section>

      <section className="nfz-main">
        {view === "3d" ? (
          <div className="nfz-map">
            <Suspense fallback={<div className="nfz-3d-loading">Loading 3D view…</div>}>
              <Nfz3DMap
                zones={zones}
                detections={visible}
                showAircraft={showAircraft}
                selectedZone={selectedZone}
                selectedId={selectedId}
                onSelectZone={selectZone}
                onSelect={selectIncursion}
              />
            </Suspense>
          </div>
        ) : (
        <div className="nfz-map">
          <MapView showAircraft={showAircraft}>
            <ZoneLayer
              zones={zones}
              hitCounts={hitCounts}
              selectedZone={selectedZone}
              onSelectZone={selectZone}
            />
            <IncursionLayer
              detections={visible}
              selectedId={selectedId}
              onSelect={selectIncursion}
            />
            <FlyTo target={flyTarget} />
          </MapView>
          <div className="nfz-legend">
            {ZONE_TYPES.filter((z) => zones.some((f) => f.properties.zone_type === z.type)).map(
              (z) => (
                <span key={z.type}>
                  <i style={{ background: z.color }} />
                  {z.label}
                </span>
              ),
            )}
            <span className="nfz-legend-note">dashed = part-time zone</span>
          </div>
        </div>
        )}

        <aside className="nfz-side">
          {selected ? (
            <IncursionDetail
              d={selected}
              zone={zoneById.get(zoneIdOf(selected))}
              now={now}
              onClose={() => setSelectedId(null)}
            />
          ) : selectedZone ? (
            <ZoneDetail
              zoneId={selectedZone}
              zone={zoneById.get(selectedZone)}
              count={hitCounts.get(selectedZone) ?? 0}
              onClose={() => selectZone(null)}
            />
          ) : (
            <ZoneList zones={zones} hitCounts={hitCounts} onSelect={selectZone} />
          )}
        </aside>
      </section>

      <section className="nfz-table-wrap">
        <div className="nfz-table-head">
          <h2>
            Incursions
            {selectedZone && <span className="nfz-pill">{selectedZone}</span>}
          </h2>
          <span className="nfz-muted">
            {visible.length} shown · last {WINDOWS.find((w) => w.hours === windowHours)?.label}
          </span>
        </div>
        {visible.length === 0 ? (
          <EmptyState
            message={
              loading && !data
                ? "Loading incursions…"
                : all.length
                  ? "No incursions match these filters."
                  : "No incursions in this window. Quiet skies."
            }
          />
        ) : (
          <div className="nfz-scroll">
            <table className="table nfz-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Severity</th>
                  <th>Aircraft</th>
                  <th>Zone</th>
                  <th>Altitude</th>
                  <th>Dwell</th>
                  <th>Started</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((d) => {
                  const alt = meta(d).extras?.altitude_ft;
                  return (
                    <tr
                      key={d.detection_id}
                      className={d.detection_id === selectedId ? "sel" : ""}
                      onClick={() => selectIncursion(d.detection_id)}
                    >
                      <td>
                        <Status d={d} />
                      </td>
                      <td>
                        <SeverityBadge severity={d.severity} />
                      </td>
                      <td className="mono">{d.entity_id}</td>
                      <td>
                        <span
                          className="nfz-type"
                          style={{ background: zoneColor(zoneTypeOf(d)) }}
                          title={zoneTypeOf(d)}
                        />
                        {zoneIdOf(d)}
                      </td>
                      <td>{typeof alt === "number" ? `${Math.round(alt).toLocaleString()} ft` : "—"}</td>
                      <td>{fmtDuration(durationSeconds(d, now))}</td>
                      <td>{new Date(d.temporal_bounds_start).toLocaleString()}</td>
                      <td>{fmtAgo(d.last_detected_at, now)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// ---- pieces --------------------------------------------------------------------

function Kpi({ label, value, alert }: { label: string; value: string | number; alert?: boolean }) {
  return (
    <div className={`nfz-kpi ${alert ? "alert" : ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

function Status({ d }: { d: Detection }) {
  return isOngoing(d) ? (
    <span className="nfz-status live">● Ongoing</span>
  ) : (
    <span className="nfz-status">Ended</span>
  );
}

function ZoneList({
  zones,
  hitCounts,
  onSelect,
}: {
  zones: ZoneFeature[];
  hitCounts: Map<string, number>;
  onSelect: (id: string) => void;
}) {
  const ranked = [...zones].sort(
    (a, b) =>
      (hitCounts.get(b.properties.zone_id) ?? 0) - (hitCounts.get(a.properties.zone_id) ?? 0) ||
      ZONE_TYPES.findIndex((z) => z.type === a.properties.zone_type) -
        ZONE_TYPES.findIndex((z) => z.type === b.properties.zone_type) ||
      a.properties.zone_id.localeCompare(b.properties.zone_id),
  );
  return (
    <>
      <h3 className="nfz-side-title">Monitored zones ({zones.length})</h3>
      <p className="nfz-muted nfz-hint">Click a zone here or on the map to focus it.</p>
      <ul className="nfz-zones">
        {ranked.map((z) => {
          const p = z.properties;
          const n = hitCounts.get(p.zone_id) ?? 0;
          return (
            <li key={p.zone_id} onClick={() => onSelect(p.zone_id)}>
              <span className="nfz-type" style={{ background: zoneColor(p.zone_type) }} />
              <span className="nfz-zone-name">
                {p.zone_id}
                <small>
                  {p.zone_type} · {fmtAltBand(p)}
                </small>
              </span>
              <span className={`nfz-count ${n ? "hot" : ""}`}>{n}</span>
            </li>
          );
        })}
      </ul>
    </>
  );
}

function ZoneDetail({
  zoneId,
  zone,
  count,
  onClose,
}: {
  zoneId: string;
  zone: ZoneFeature | undefined;
  count: number;
  onClose: () => void;
}) {
  const p = zone?.properties;
  return (
    <>
      <div className="nfz-side-bar">
        <button className="nfz-link" onClick={onClose}>
          ← All zones
        </button>
      </div>
      <h3 className="nfz-side-title">
        <span className="nfz-type" style={{ background: zoneColor(p?.zone_type) }} />
        {zoneId}
      </h3>
      {p?.name && p.name !== zoneId && <p className="nfz-muted">{p.name}</p>}
      <dl className="nfz-dl">
        <dt>Incursions</dt>
        <dd>{count}</dd>
        {p && (
          <>
            <dt>Type</dt>
            <dd>{p.zone_type}</dd>
            <dt>Altitudes</dt>
            <dd>{fmtAltBand(p)}</dd>
            <dt>Active</dt>
            <dd>{p.activation === "ALWAYS" ? "Always" : (p.times_of_use ?? p.activation ?? "—")}</dd>
            {p.controlling_agency && (
              <>
                <dt>Controlled by</dt>
                <dd>{p.controlling_agency}</dd>
              </>
            )}
            <dt>Source</dt>
            <dd>
              {p.source === "demo" ? "Demo zone (not real airspace)" : (p.source ?? "—")}
              {p.source_asof ? ` · as of ${p.source_asof}` : ""}
            </dd>
          </>
        )}
      </dl>
    </>
  );
}

function IncursionDetail({
  d,
  zone,
  now,
  onClose,
}: {
  d: Detection;
  zone: ZoneFeature | undefined;
  now: number;
  onClose: () => void;
}) {
  const m = meta(d);
  const ex = m.extras ?? {};
  return (
    <>
      <div className="nfz-side-bar">
        <button className="nfz-link" onClick={onClose}>
          ← Back
        </button>
        <Status d={d} />
      </div>
      <h3 className="nfz-side-title mono">{d.entity_id}</h3>
      <p className="nfz-muted">
        in <b style={{ color: zoneColor(zoneTypeOf(d)) }}>{zoneNameOf(d)}</b> ({zoneTypeOf(d)})
      </p>
      <dl className="nfz-dl">
        <dt>Severity</dt>
        <dd>
          <SeverityBadge severity={d.severity} />
        </dd>
        <dt>Confidence</dt>
        <dd>{typeof d.confidence === "number" ? `${Math.round(d.confidence * 100)}%` : "—"}</dd>
        {typeof m.anomaly_score === "number" && (
          <>
            <dt>Anomaly score</dt>
            <dd>{m.anomaly_score.toFixed(3)}</dd>
          </>
        )}
        <dt>Dwell</dt>
        <dd>{fmtDuration(durationSeconds(d, now))}</dd>
        {typeof ex.altitude_ft === "number" && (
          <>
            <dt>Altitude</dt>
            <dd>{Math.round(ex.altitude_ft).toLocaleString()} ft</dd>
          </>
        )}
        {typeof ex.penetration_nm === "number" && (
          <>
            <dt>Depth inside</dt>
            <dd>{Math.abs(ex.penetration_nm).toFixed(2)} nm</dd>
          </>
        )}
        {zone && (
          <>
            <dt>Zone altitudes</dt>
            <dd>{fmtAltBand(zone.properties)}</dd>
          </>
        )}
        <dt>Started</dt>
        <dd>{new Date(d.temporal_bounds_start).toLocaleString()}</dd>
        <dt>Ended</dt>
        <dd>{d.temporal_bounds_end ? new Date(d.temporal_bounds_end).toLocaleString() : "—"}</dd>
      </dl>
      {m.explanation_facts?.length ? (
        <>
          <h4>Why it fired</h4>
          <ul className="nfz-facts">
            {m.explanation_facts.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </>
      ) : null}
      {m.limitations?.length ? (
        <>
          <h4>Caveats</h4>
          <ul className="nfz-facts muted">
            {m.limitations.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}
