// Detections console (v1). Mirrors the SENTINEL Trust Console's master-detail
// idea: a scrollable queue of every detection on the left, and the full "case"
// for the selected one on the right. SkyWatch has no Trust Confidence Engine
// yet, so the right panel shows the detection's general information (its stored
// fields, the detector's own evidence/metadata, and its detector-specific
// columns) with a reserved slot where the trust assessment will later live.
//
// This is SHARED platform UI: it reads all three detector feeds. It never
// changes a team's endpoint or page — it merges what the existing hooks return.
import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  useSpoofingDetections,
  useProximityDetections,
  useNoFlyZoneDetections,
} from "../api/hooks";
import type { Detection } from "../api/types";
import { SeverityBadge } from "../components/SeverityBadge";
import { EmptyState } from "../components/EmptyState";
import { config } from "../config";

// How far back the console looks, and the cap per detector feed.
const SINCE_HOURS = 24;
const PER_DETECTOR_LIMIT = 200;

type DetectorKey = "spoofing" | "proximity" | "no-fly-zone";

const DETECTOR_LABEL: Record<DetectorKey, string> = {
  spoofing: "Spoofing",
  proximity: "Proximity",
  "no-fly-zone": "No-fly zone",
};

// A queue row is a detection tagged with which detector it came from, so one
// merged list can show all three and still colour/filter by detector.
interface CaseRow extends Detection {
  _detector: DetectorKey;
}

// Columns every detection shares (rendered in the "Case details" block) plus
// the fields we render elsewhere or never want in the generic dump. Anything
// NOT in here is treated as a detector-specific column and shown automatically,
// so each team's own columns appear without this page knowing about them.
const COMMON_OR_HANDLED = new Set<string>([
  "detection_id",
  "detector_id",
  "detector_version",
  "detection_type",
  "severity",
  "confidence",
  "entity_id",
  "latitude",
  "longitude",
  "temporal_bounds_start",
  "temporal_bounds_end",
  "last_detected_at",
  "evidence",
  "metadata",
  "geospatial_context",
  "tags",
  "_detector",
  // Plumbing/infra columns some detector tables carry: these just duplicate the
  // row or hold pipeline bookkeeping, so they'd bury the real findings. Skipped
  // from the auto-discovered "detector details" dump.
  "raw_detection",
  "provenance",
  "dedup_key",
  "dedup_scope",
  "created_at",
  "ingestion_timestamp",
  "source_record_id",
]);

function shortTime(iso: unknown): string {
  if (typeof iso !== "string" || !iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString();
}

function confidencePct(value: unknown): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "—";
}

// A human label for a value that may be a scalar, object, or array.
function renderValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function isEmptyJson(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (typeof value === "object") return Object.keys(value as object).length === 0;
  if (typeof value === "string") return value.trim() === "";
  return false;
}

export function CasesPage() {
  const spoof = useSpoofingDetections({ since_hours: SINCE_HOURS, limit: PER_DETECTOR_LIMIT });
  const prox = useProximityDetections({ since_hours: SINCE_HOURS, limit: PER_DETECTOR_LIMIT });
  const nfz = useNoFlyZoneDetections({ since_hours: SINCE_HOURS, limit: PER_DETECTOR_LIMIT });

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [detectorFilter, setDetectorFilter] = useState<DetectorKey | "all">("all");
  const [severityFilter, setSeverityFilter] = useState<string>("all");

  // Re-poll all three feeds on the shared cadence so new detections age in and
  // old ones drop off, mirroring the console's periodic reload.
  const reloadRef = useRef<() => void>(() => {});
  reloadRef.current = () => {
    spoof.reload();
    prox.reload();
    nfz.reload();
  };
  useEffect(() => {
    const id = window.setInterval(() => reloadRef.current(), config.refreshIntervalMs);
    return () => window.clearInterval(id);
  }, []);

  // Merge the three feeds into one list, newest first.
  const rows: CaseRow[] = useMemo(() => {
    const tag = (list: Detection[] | null, key: DetectorKey): CaseRow[] =>
      (list ?? []).map((d) => ({ ...d, _detector: key }));
    const all = [
      ...tag(spoof.data, "spoofing"),
      ...tag(prox.data, "proximity"),
      ...tag(nfz.data, "no-fly-zone"),
    ];
    all.sort((a, b) => {
      const ta = new Date(a.last_detected_at).getTime() || 0;
      const tb = new Date(b.last_detected_at).getTime() || 0;
      return tb - ta;
    });
    return all;
  }, [spoof.data, prox.data, nfz.data]);

  const loading = spoof.loading && prox.loading && nfz.loading;
  // Only treat it as an error state if every feed failed; a single detector
  // being down shouldn't blank the whole console.
  const allErrored = Boolean(spoof.error && prox.error && nfz.error);

  const severities = useMemo(() => {
    const seen = new Set<string>();
    rows.forEach((r) => r.severity && seen.add(r.severity.toLowerCase()));
    return Array.from(seen);
  }, [rows]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((r) => {
      if (detectorFilter !== "all" && r._detector !== detectorFilter) return false;
      if (severityFilter !== "all" && (r.severity ?? "").toLowerCase() !== severityFilter) return false;
      if (!q) return true;
      const hay = [r.entity_id, r.detector_id, r.detection_type, r._detector]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [rows, query, detectorFilter, severityFilter]);

  // Keep the selection valid as the list refreshes; default to the first row.
  const selected = visible.find((r) => r.detection_id === selectedId) ?? null;
  useEffect(() => {
    if (!selected && visible.length) setSelectedId(visible[0].detection_id);
    if (!visible.length) setSelectedId(null);
  }, [visible, selected]);

  return (
    <div className="cases-shell">
      {/* ---- Queue (left) ---- */}
      <section className="cases-queue">
        <div className="cases-queue__head">
          <h1>Detections</h1>
          <span className="cases-count">
            {loading ? "loading…" : `${visible.length} shown`}
          </span>
        </div>

        <div className="cases-search">
          <input
            placeholder="Search aircraft, detector, type"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <div className="cases-filters">
            <button
              className={`chip ${detectorFilter === "all" ? "active" : ""}`}
              onClick={() => setDetectorFilter("all")}
            >
              All
            </button>
            {(Object.keys(DETECTOR_LABEL) as DetectorKey[]).map((k) => (
              <button
                key={k}
                className={`chip ${detectorFilter === k ? "active" : ""}`}
                onClick={() => setDetectorFilter(k)}
              >
                {DETECTOR_LABEL[k]}
              </button>
            ))}
          </div>
          {severities.length > 0 && (
            <div className="cases-filters">
              <button
                className={`chip ${severityFilter === "all" ? "active" : ""}`}
                onClick={() => setSeverityFilter("all")}
              >
                Any severity
              </button>
              {severities.map((s) => (
                <button
                  key={s}
                  className={`chip ${severityFilter === s ? "active" : ""}`}
                  onClick={() => setSeverityFilter(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="cases-rows">
          {allErrored ? (
            <EmptyState kind="error" message="Every detector feed failed to load." />
          ) : loading ? (
            <EmptyState message="Loading detections…" />
          ) : !visible.length ? (
            <EmptyState message="No detections match the current filters." />
          ) : (
            visible.map((r) => (
              <button
                key={r.detection_id}
                className={`cases-row ${selected?.detection_id === r.detection_id ? "active" : ""}`}
                onClick={() => setSelectedId(r.detection_id)}
              >
                <div className="cases-row__top">
                  <span className="cases-row__entity">{r.entity_id || "unknown"}</span>
                  <SeverityBadge severity={r.severity} />
                </div>
                <div className="cases-row__meta">
                  {DETECTOR_LABEL[r._detector]} · {r.detection_type || "detection"}
                </div>
                <div className="cases-row__meta">
                  conf {confidencePct(r.confidence)} · {shortTime(r.last_detected_at)}
                </div>
              </button>
            ))
          )}
        </div>
      </section>

      {/* ---- Case detail (right) ---- */}
      <section className="cases-case">
        {!selected ? (
          <EmptyState message="Select a detection to see its case." />
        ) : (
          <CaseDetail row={selected} />
        )}
      </section>
    </div>
  );
}

function CaseDetail({ row }: { row: CaseRow }) {
  // Detector-specific columns: anything on the row that isn't a common/handled
  // field. This surfaces each team's own columns (e.g. proximity's
  // predicted_horizontal_nm, NFZ's zone_name) without hard-coding them.
  const extraColumns = Object.entries(row).filter(
    ([k, v]) => !COMMON_OR_HANDLED.has(k) && v !== null && v !== undefined,
  );

  return (
    <div className="cases-detail">
      <header className="cases-detail__head">
        <div>
          <h1>{row.entity_id || "Unknown aircraft"}</h1>
          <div className="cases-detail__sub">
            {DETECTOR_LABEL[row._detector]} · {row.detection_type || "detection"} ·{" "}
            {row.detector_id}
            {row.detector_version ? ` (${row.detector_version})` : ""}
          </div>
        </div>
        <SeverityBadge severity={row.severity} />
      </header>

      {/* Core stored fields — the "general information from the case". */}
      <section className="cases-block">
        <h3>Case details</h3>
        <div className="cases-fields">
          <Field label="Severity" value={row.severity} />
          <Field label="Confidence" value={confidencePct(row.confidence)} />
          <Field label="Aircraft (entity)" value={row.entity_id} />
          <Field label="Detector" value={row.detector_id} />
          <Field
            label="Position"
            value={
              row.latitude != null && row.longitude != null
                ? `${row.latitude.toFixed(4)}, ${row.longitude.toFixed(4)}`
                : "—"
            }
          />
          <Field label="First seen" value={shortTime(row.temporal_bounds_start)} />
          <Field label="Last seen" value={shortTime(row.last_detected_at)} />
          <Field label="Detection ID" value={row.detection_id} mono />
        </div>
        {row.latitude != null && row.longitude != null && (
          <Link className="cases-maplink" to="/map">
            View the live map →
          </Link>
        )}
      </section>

      {/* The detector's own explanation — shown, not re-judged. */}
      {(!isEmptyJson(row.evidence) || !isEmptyJson(row.metadata)) && (
        <section className="cases-block">
          <h3>Why it fired</h3>
          {!isEmptyJson(row.evidence) && (
            <>
              <div className="cases-sublabel">Evidence</div>
              <pre className="cases-json">{renderValue(row.evidence)}</pre>
            </>
          )}
          {!isEmptyJson(row.metadata) && (
            <>
              <div className="cases-sublabel">Metadata</div>
              <pre className="cases-json">{renderValue(row.metadata)}</pre>
            </>
          )}
        </section>
      )}

      {/* Detector-specific columns, auto-discovered from the row. */}
      {extraColumns.length > 0 && (
        <section className="cases-block">
          <h3>{DETECTOR_LABEL[row._detector]} details</h3>
          <div className="cases-fields">
            {extraColumns.map(([k, v]) =>
              typeof v === "object" ? (
                <div className="cases-field cases-field--wide" key={k}>
                  <span className="cases-field__label">{k}</span>
                  <pre className="cases-json">{renderValue(v)}</pre>
                </div>
              ) : (
                <Field key={k} label={k} value={String(v)} />
              ),
            )}
          </div>
        </section>
      )}

      {/* Reserved slot: the Trust Confidence Engine assessment lands here. */}
      <section className="cases-block cases-tce">
        <h3>Trust assessment</h3>
        <p className="cases-tce__note">
          The trust confidence engine isn't wired up yet. Its composite score,
          layer breakdown, and gate results will appear here.
        </p>
      </section>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
}: {
  label: string;
  value: unknown;
  mono?: boolean;
}) {
  return (
    <div className="cases-field">
      <span className="cases-field__label">{label}</span>
      <span className={`cases-field__value ${mono ? "mono" : ""}`}>
        {value === null || value === undefined || value === "" ? "—" : String(value)}
      </span>
    </div>
  );
}
