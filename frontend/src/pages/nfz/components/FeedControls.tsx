// Filters for the feed. Every one is kept in the address bar (shareable).
import type { RefObject } from "react";
import { RANGES, SEVERITIES, type NfzState } from "../urlState";

export function FeedControls({
  state,
  update,
  zoneTypes,
  loading,
  onRefresh,
  onExport,
  exportCount,
  searchRef,
}: {
  state: NfzState;
  update: (p: Partial<NfzState>) => void;
  zoneTypes: string[];
  loading: boolean;
  onRefresh: () => void;
  onExport: () => void;
  exportCount: number;
  searchRef: RefObject<HTMLInputElement>;
}) {
  return (
    <div className="nfz-controls">
      <label className="nfz-field">
        Time range
        <select value={state.hours} onChange={(e) => update({ hours: Number(e.target.value) })} className="nfz-input">
          {RANGES.map((r) => (
            <option key={r.hours} value={r.hours}>
              Last {r.label}
            </option>
          ))}
        </select>
      </label>
      <label className="nfz-field">
        Severity
        <select value={state.severity} onChange={(e) => update({ severity: e.target.value })} className="nfz-input">
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s || "All"}
            </option>
          ))}
        </select>
      </label>
      <label className="nfz-field">
        Zone type
        <select value={state.zoneType} onChange={(e) => update({ zoneType: e.target.value })} className="nfz-input">
          <option value="">All</option>
          {zoneTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="nfz-field nfz-field--grow">
        <span className="nfz-field-label">
          Search aircraft or zone <kbd className="nfz-kbd">/</kbd>
        </span>
        <input
          ref={searchRef}
          value={state.search}
          onChange={(e) => update({ search: e.target.value })}
          placeholder="icao24:a1b2c3, P-56, DEMO-1…"
          className="nfz-input"
          type="search"
        />
      </label>
      <div className="nfz-controls-actions">
        <button className="btn ghost" onClick={onRefresh} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
        <button className="btn ghost" onClick={onExport} disabled={!exportCount} title="Download what the feed shows as a CSV file">
          Export CSV
        </button>
      </div>
    </div>
  );
}
