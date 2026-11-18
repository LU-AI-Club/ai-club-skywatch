// NO-FLY-ZONE TEAM page (/no-fly-zone). Shows incursions into restricted,
// prohibited and MOA airspace, whether the detector and the aircraft feed are
// alive, a live airspace map, and a detail panel with a replay of each
// incursion. The pieces live in ./nfz/ (see ./nfz/README.md).
//
// Zone polygons come from public/airspace/ (copied from
// air/detectors/no_fly_zone/fixtures/airspace/), not the API.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useDetectorRuns, useNoFlyZoneDetections } from "../api/hooks";
import type { Detection } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { useNfzUrlState, RANGES } from "./nfz/urlState";
import { TYPE_ORDER, useZones } from "./nfz/zones";
import { duration } from "./nfz/format";
import { downloadCsv } from "./nfz/csv";
import { useFreshIds } from "./nfz/hooks/useFreshIds";
import { useFeedHealth } from "./nfz/hooks/useFeedHealth";
import { useAlerts } from "./nfz/hooks/useAlerts";
import { useHotkeys } from "./nfz/hooks/useHotkeys";
import { Header } from "./nfz/components/Header";
import { Readout } from "./nfz/components/Readout";
import { Timeline } from "./nfz/components/Timeline";
import { ZoneBoard } from "./nfz/components/ZoneBoard";
import { ZoneDetail } from "./nfz/components/ZoneDetail";
import { FeedControls } from "./nfz/components/FeedControls";
import { IncursionTable } from "./nfz/components/IncursionTable";
import { DetailPanel } from "./nfz/components/DetailPanel";
import { AirspaceMap, type AirspaceMapHandle } from "./nfz/components/AirspaceMap";
import { HotkeyHelp } from "./nfz/components/HotkeyHelp";
import { config } from "../config";
// Sectional-chart look: fonts bundled with the app, styles scoped under .nfz.
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "./nfz/nfz.css";

const DETECTOR_ID = "skywatch.no_fly_zone";

export function NoFlyZonePage() {
  // Filters + selection live in the address bar, so links are shareable.
  const [state, update] = useNfzUrlState();
  const [help, setHelp] = useState(false);
  const [flyPoint, setFlyPoint] = useState<{ lat: number; lon: number; key: string } | null>(null);
  const mapRef = useRef<AirspaceMapHandle>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const feedRef = useRef<HTMLDivElement>(null);

  const { data, loading, error, reload } = useNoFlyZoneDetections({
    since_hours: state.hours,
    severity: state.severity || undefined,
  });
  const runs = useDetectorRuns({ detector_id: DETECTOR_ID, limit: 1 });
  const zones = useZones();
  const health = useFeedHealth();

  // Keep detections and detector status fresh while the page is open.
  const reloadRuns = runs.reload;
  useEffect(() => {
    const id = window.setInterval(() => {
      reload();
      reloadRuns();
    }, 30_000);
    return () => window.clearInterval(id);
  }, [reload, reloadRuns]);

  const all = useMemo(() => data ?? [], [data]);
  const zoneTypes = useMemo(
    () => [...new Set(all.map((d) => String(d.zone_type ?? "")).filter(Boolean))].sort(),
    [all],
  );
  const rows = useMemo(() => {
    const q = state.search.trim().toLowerCase();
    return all.filter(
      (d) =>
        (!state.zoneType || String(d.zone_type ?? "").toUpperCase() === state.zoneType) &&
        (!state.zone || d.zone_id === state.zone) &&
        (!q ||
          d.entity_id.toLowerCase().includes(q) ||
          String(d.zone_id ?? "").toLowerCase().includes(q) ||
          String(d.zone_name ?? "").toLowerCase().includes(q)),
    );
  }, [all, state.search, state.zoneType, state.zone]);

  const selected = useMemo(() => all.find((d) => d.detection_id === state.selected) ?? null, [all, state.selected]);
  const selectedMissing = !!state.selected && !!data && !selected;

  const stats = useMemo(() => {
    const aircraft = new Set(rows.map((d) => d.entity_id));
    const open = rows.filter((d) => !d.temporal_bounds_end).length;
    const longest = rows.reduce((m, d) => Math.max(m, Number(d.duration_seconds) || 0), 0);
    return { aircraft: aircraft.size, open, longest };
  }, [rows]);

  // Incursions per zone (time range + severity applied, other filters not),
  // so the board always shows the whole picture.
  const zoneCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const d of all) m.set(String(d.zone_id ?? ""), (m.get(String(d.zone_id ?? "")) ?? 0) + 1);
    return m;
  }, [all]);
  const board = useMemo(
    () =>
      [...zones].sort(
        (a, b) =>
          (zoneCounts.get(b.id) ?? 0) - (zoneCounts.get(a.id) ?? 0) ||
          (TYPE_ORDER[a.type] ?? 9) - (TYPE_ORDER[b.type] ?? 9) ||
          a.id.localeCompare(b.id),
      ),
    [zones, zoneCounts],
  );
  const activeZones = board.filter((z) => (zoneCounts.get(z.id) ?? 0) > 0).length;
  const focusZone = zones.find((z) => z.id === state.zone) ?? null;
  const zoneById = useMemo(() => new Map(zones.map((z) => [z.id, z])), [zones]);

  // New incursions: ripple on the map, flash their zone card and feed row,
  // and (if turned on) sound + notification.
  const fresh = useFreshIds(data);
  const pingedZones = useMemo(
    () => new Set(all.filter((d) => fresh.has(d.detection_id)).map((d) => String(d.zone_id ?? ""))),
    [all, fresh],
  );
  const alerts = useAlerts(fresh, all);

  // Incursions per time slice across the range, for the readout sparkline.
  const spark = useMemo(() => {
    const n = 36;
    const end = Date.now();
    const start = end - state.hours * 3_600_000;
    const bins = new Array<number>(n).fill(0);
    for (const d of rows) {
      const t = Date.parse(String(d.temporal_bounds_start ?? d.last_detected_at));
      if (!Number.isFinite(t) || t < start) continue;
      bins[Math.min(n - 1, Math.floor(((t - start) / (end - start)) * n))]++;
    }
    return bins;
  }, [rows, state.hours]);

  const rangeLabel = RANGES.find((r) => r.hours === state.hours)?.label ?? `${state.hours} h`;
  const firstLoad = loading && !data;

  const select = useCallback((d: Detection) => update({ selected: d.detection_id }), [update]);
  const selectFromMap = useCallback(
    (d: Detection) => {
      update({ selected: d.detection_id });
      window.setTimeout(() => feedRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    },
    [update],
  );
  const pickZone = useCallback((id: string) => update({ zone: id }), [update]);
  const toggleZone = useCallback((id: string) => update({ zone: state.zone === id ? "" : id }), [update, state.zone]);

  // Keyboard shortcuts.
  const step = (dir: 1 | -1) => {
    if (!rows.length) return;
    const i = rows.findIndex((d) => d.detection_id === state.selected);
    const next = rows[i === -1 ? 0 : Math.min(rows.length - 1, Math.max(0, i + dir))];
    update({ selected: next.detection_id });
    document.querySelector(`[data-detection="${CSS.escape(next.detection_id)}"]`)?.scrollIntoView({ block: "nearest" });
  };
  useHotkeys({
    j: () => step(1),
    k: () => step(-1),
    f: () => mapRef.current?.toggleFullscreen(),
    "/": () => searchRef.current?.focus(),
    "?": () => setHelp((h) => !h),
    Escape: (e) => {
      if (help) setHelp(false);
      else if (document.activeElement === searchRef.current) searchRef.current?.blur();
      else if (state.selected) update({ selected: "" });
      else if (state.zone) update({ zone: "" });
      else if (e.target instanceof HTMLElement) e.target.blur();
    },
  });

  const emptyMessage = error
    ? "Couldn't load incursions."
    : runs.data?.[0]?.status?.toUpperCase() === "SUCCESS"
      ? "No incursions in this window — the detector is running, the sky is clear."
      : "No incursions for the current filters.";

  return (
    <div className="nfz">
      <div className="page">
        <Header
          runs={runs.data}
          runsError={runs.error}
          health={health}
          alertsOn={alerts.enabled}
          alertsBlocked={alerts.permission === "denied"}
          onToggleAlerts={() => void alerts.toggle()}
          onHelp={() => setHelp(true)}
        />

        {error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}

        <div className="nfz-readouts">
          <Readout label={`Incursions · ${rangeLabel}`} value={rows.length} loading={firstLoad} alert={stats.open > 0} spark={spark} />
          <Readout label="Active zones" value={zones.length ? `${activeZones} / ${zones.length}` : "—"} loading={firstLoad} />
          <Readout label="Aircraft involved" value={stats.aircraft} loading={firstLoad} />
          <Readout label="Longest time inside" value={duration(stats.longest)} loading={firstLoad} />
        </div>

        <div className="nfz-section-head">
          <span>Timeline</span>
          <span className="nfz-meta">last {rangeLabel} · click a mark for details</span>
        </div>
        <Timeline rows={rows} hours={state.hours} selectedId={selected?.detection_id ?? null} onSelect={select} />

        <div className="nfz-situation">
          <section className="nfz-mapcol">
            <div className="nfz-section-head">
              <span>Airspace picture</span>
              <span className="nfz-meta">
                live · updates every {Math.round(config.refreshIntervalMs / 1000)} s · click map to scroll-zoom
              </span>
            </div>
            <AirspaceMap
              ref={mapRef}
              rows={rows}
              selectedId={selected?.detection_id ?? null}
              fresh={fresh}
              focusZone={focusZone}
              flyPoint={flyPoint}
              health={health}
              onSelect={selectFromMap}
              onZoneClick={pickZone}
            />
          </section>

          <section className="nfz-boardcol">
            <div className="nfz-section-head">
              <span>Zone board</span>
              {state.zone ? (
                <button className="nfz-clear" onClick={() => update({ zone: "" })}>
                  Showing {state.zone} only · show all
                </button>
              ) : (
                <span className="nfz-meta">click a zone for details</span>
              )}
            </div>
            <ZoneBoard zones={board} counts={zoneCounts} focusId={state.zone} pinged={pingedZones} onPick={toggleZone} />
          </section>
        </div>

        {focusZone && (
          <ZoneDetail
            zone={focusZone}
            detections={all.filter((d) => d.zone_id === focusZone.id)}
            rangeLabel={rangeLabel}
            onClose={() => update({ zone: "" })}
            onSelect={select}
          />
        )}

        <div ref={feedRef} className="nfz-feed-anchor" />
        <FeedControls
          state={state}
          update={update}
          zoneTypes={zoneTypes}
          loading={loading}
          onRefresh={reload}
          onExport={() => downloadCsv(rows)}
          exportCount={rows.length}
          searchRef={searchRef}
        />

        <div className="nfz-section-head">
          <span>Incursion feed</span>
          <span className="nfz-meta">
            {rows.length} shown · <kbd className="nfz-kbd">J</kbd>/<kbd className="nfz-kbd">K</kbd> to step through
          </span>
        </div>
        {selectedMissing && (
          <div className="nfz-banner is-warn">
            <b>Not in this time range</b> The linked incursion isn't in the last {rangeLabel}.{" "}
            {state.hours < 720 && (
              <button className="nfz-clear" onClick={() => update({ hours: 720 })}>
                Look in the last 30 days
              </button>
            )}
          </div>
        )}
        <div className="nfz-feed">
          <div className="nfz-feed-table">
            <IncursionTable
              rows={rows}
              loading={loading}
              hasData={!!data}
              selectedId={selected?.detection_id ?? null}
              fresh={fresh}
              emptyMessage={emptyMessage}
              onSelect={select}
            />
          </div>
          {selected && (
            <DetailPanel
              key={selected.detection_id}
              detection={selected}
              zone={zoneById.get(String(selected.zone_id ?? ""))}
              onClose={() => update({ selected: "" })}
              onShowOnMap={() => {
                if (typeof selected.latitude !== "number" || typeof selected.longitude !== "number") return;
                setFlyPoint({ lat: selected.latitude, lon: selected.longitude, key: `${selected.detection_id}-${Date.now()}` });
                document.querySelector(".nfz-map")?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
            />
          )}
        </div>
      </div>
      {help && <HotkeyHelp onClose={() => setHelp(false)} />}
    </div>
  );
}
