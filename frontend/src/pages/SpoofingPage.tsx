// SPOOFING TEAM — our dashboard.
//
// The three deliverables, in the order a reader needs them:
//   2c  is it alive right now   -> spoofing/DetectorHealth
//   2b  what it found, and why  -> spoofing/GateBreakdown, FindingsTable, DetectionDetail
//   2a  what it does            -> spoofing/AlgorithmPanel
//
// Health sits above the findings on purpose. The first question anyone asks of
// an empty table is "is this broken?", and answering that after showing them
// the empty table answers it too late.
//
// Every panel is its own file, so several of us can work at once without
// colliding. This file only arranges them and holds the state they share: the
// filters, and which finding is open.
import { useMemo, useState } from "react";
import { useSpoofingDetections } from "../api/hooks";
import { StatCard } from "../components/StatCard";
import { EmptyState } from "../components/EmptyState";
import type { Detection } from "../api/types";
import { AlgorithmPanel } from "./spoofing/AlgorithmPanel";
import { DetectorHealth } from "./spoofing/DetectorHealth";
import { GateBreakdown } from "./spoofing/GateBreakdown";
import { FindingsTable } from "./spoofing/FindingsTable";
import { DetectionDetail } from "./spoofing/DetectionDetail";
import "./spoofing/spoofing.css";

const RANGES = [
  { hours: 1, label: "1h" },
  { hours: 6, label: "6h" },
  { hours: 24, label: "24h" },
  { hours: 72, label: "3d" },
  // A week, because findings are rare: at a handful an hour a 24h window can
  // genuinely be empty, and "nothing today" is a different question from
  // "nothing this week".
  { hours: 168, label: "7d" },
] as const;

const SEVERITIES = ["HIGH", "MEDIUM", "LOW"] as const;

export function SpoofingPage() {
  const [hours, setHours] = useState<number>(24);
  const [severity, setSeverity] = useState<string | null>(null);
  const [gate, setGate] = useState<string | null>(null);
  const [open, setOpen] = useState<Detection | null>(null);

  // `gate` is ours — see api/main.py. The shared endpoint cannot filter on it
  // because it lives inside metadata, not in a column.
  const { data, loading, error, reload } = useSpoofingDetections({
    since_hours: hours,
    severity: severity ?? undefined,
    gate: gate ?? undefined,
  });

  const rows = useMemo(() => data ?? [], [data]);

  const stats = useMemo(() => {
    const aircraft = new Set(rows.map((d) => d.entity_id)).size;
    const high = rows.filter((d) =>
      ["high", "critical"].includes(String(d.severity).toLowerCase()),
    ).length;
    return { aircraft, high, perHour: hours > 0 ? rows.length / hours : 0 };
  }, [rows, hours]);

  return (
    <div className="page spoofing-page">
      <div className="page-head">
        <h1>Spoofing</h1>
        <p className="owner">
          Aircraft whose broadcasts disagree with themselves — with physics, or
          with who they claim to be.
        </p>
      </div>

      {/* 2c — first, so an empty table below is never ambiguous. */}
      <DetectorHealth />

      {error && <EmptyState kind="error" message={`Couldn't load detections: ${error}`} />}

      <div className="controls">
        <div className="seg" role="group" aria-label="Time range">
          {RANGES.map((r) => (
            <button
              key={r.hours}
              className={`seg-btn ${hours === r.hours ? "on" : ""}`}
              onClick={() => setHours(r.hours)}
            >
              {r.label}
            </button>
          ))}
        </div>

        <div className="seg" role="group" aria-label="Severity">
          <button
            className={`seg-btn ${severity === null ? "on" : ""}`}
            onClick={() => setSeverity(null)}
          >
            All
          </button>
          {SEVERITIES.map((s) => (
            <button
              key={s}
              className={`seg-btn ${severity === s ? "on" : ""}`}
              onClick={() => setSeverity(severity === s ? null : s)}
            >
              {s}
            </button>
          ))}
        </div>
      <SpoofingSummary detections={rows} windowHours={24} />

        <button className="btn ghost" onClick={reload} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </button>
      </div>

      <div className="stat-grid">
        <StatCard label={`Findings (${hours}h)`} value={loading ? "…" : rows.length} />
        <StatCard label="Aircraft involved" value={loading ? "…" : stats.aircraft} />
        <StatCard label="High severity" value={loading ? "…" : stats.high} />
        <StatCard label="Per hour" value={loading ? "…" : stats.perHour.toFixed(1)} />
      </div>

      {/* 2b — which rules fired. Clicking one filters the table below. */}
      <GateBreakdown sinceHours={hours} selected={gate} onSelect={setGate} />

      <section className="findings">
        <div className="findings-head">
          <h2>Findings</h2>
          {gate && (
            <button className="btn ghost small" onClick={() => setGate(null)}>
              Filtered to {gate} — show all
            </button>
          )}
        </div>

        {!loading && rows.length === 0 ? (
          <EmptyState message="Nothing found in this window. For this detector that is the normal state — see the status above." />
        ) : (
          <>
            <p className="hint">Click a finding to see why it fired.</p>
            <FindingsTable
              detections={rows}
              selectedId={open?.detection_id ?? null}
              onSelect={setOpen}
            />
          </>
        )}
      </section>

      {/* 2a — how it works. Last, because it is reference rather than news. */}
      <AlgorithmPanel />

      <DetectionDetail detection={open} onClose={() => setOpen(null)} />
    </div>
  );
}