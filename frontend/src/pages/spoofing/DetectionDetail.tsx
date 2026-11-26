// Deliverable 2b — one finding in full.
//
// The table row is a summary. This is where the detector's reasoning actually
// becomes visible, and it is the part of the page that could not be built by
// any other team: our table has no detector-specific columns, so everything
// that explains a finding lives inside `metadata` and `evidence`.
//
// The rule here is display, never re-judge. The detector already decided this
// fired, already measured the value against its threshold, and already wrote
// the explanation in plain English. A page that recomputed any of that could
// disagree with the detector, and then there would be two answers.
import type { Detection } from "../../api/types";
import { SPOOFING_GATES } from "./AlgorithmPanel";

const NAMES = new Map(SPOOFING_GATES.map((g) => [g.gate, g.name]));
const QUESTIONS = new Map(SPOOFING_GATES.map((g) => [g.gate, g.question]));

function meta(d: Detection): Record<string, unknown> {
  const m = d.metadata;
  return m && typeof m === "object" ? (m as Record<string, unknown>) : {};
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function list(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

function when(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? String(iso) : t.toLocaleString();
}

export function DetectionDetail({
  detection,
  onClose,
}: {
  detection: Detection | null;
  onClose: () => void;
}) {
  if (!detection) return null;

  const m = meta(detection);
  const gate = str(m.gate);
  const event = (m.event && typeof m.event === "object" ? m.event : {}) as Record<string, unknown>;

  const measured = num(event.measured);
  const threshold = num(event.threshold);
  const unit = str(event.unit) ?? "";
  const score = num(m.anomaly_score);
  const facts = list(m.explanation_facts);
  const limits = list(m.limitations);

  // How far past the line it went. The detector's own severity already
  // reflects this, but the ratio is what makes "barely" visible: a finding
  // 0.02% over its threshold and one at triple it are both "fired".
  const over =
    measured !== null && threshold !== null && threshold !== 0
      ? ((measured - threshold) / Math.abs(threshold)) * 100
      : null;

  return (
    <aside className="detail" role="dialog" aria-label="Detection detail">
      <header className="detail-head">
        <div>
          <h2>{gate ? (NAMES.get(gate) ?? gate) : detection.detection_type}</h2>
          <code className="detail-id">{detection.entity_id}</code>
        </div>
        <button className="btn ghost" onClick={onClose} aria-label="Close">
          ✕
        </button>
      </header>

      {gate && QUESTIONS.has(gate) && (
        <p className="detail-what">{QUESTIONS.get(gate)}</p>
      )}

      {/* The measurement, in the detector's own units. */}
      {measured !== null && threshold !== null && (
        <div className="detail-measure">
          <div>
            <span className="muted">measured</span>
            <strong>
              {measured.toFixed(2)} {unit}
            </strong>
          </div>
          <div>
            <span className="muted">limit</span>
            <strong>
              {threshold.toFixed(2)} {unit}
            </strong>
          </div>
          {over !== null && (
            <div>
              <span className="muted">over by</span>
              <strong className={over < 1 ? "thin" : undefined}>
                {over < 1 ? over.toFixed(2) : over.toFixed(0)}%
              </strong>
            </div>
          )}
        </div>
      )}

      {over !== null && over < 1 && (
        <p className="detail-caveat">
          This one only just crossed its threshold. Treat it as weak evidence —
          a slightly different reading would not have fired it.
        </p>
      )}

      {/* Written by the detector at the moment it fired. Shown verbatim. */}
      {facts.length > 0 && (
        <>
          <h3>What was observed</h3>
          <ul className="detail-facts">
            {facts.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </>
      )}

      {/* The detector states what it cannot tell you. Hiding this would make
          the finding look more certain than it is. */}
      {limits.length > 0 && (
        <>
          <h3>What this does not tell you</h3>
          <ul className="detail-limits">
            {limits.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </>
      )}

      <h3>Details</h3>
      <dl className="detail-grid">
        <dt>Severity</dt>
        <dd>{detection.severity}</dd>
        <dt>Confidence</dt>
        <dd>
          {typeof detection.confidence === "number" ? detection.confidence.toFixed(2) : "—"}
          {score !== null && <span className="muted"> (anomaly {score.toFixed(2)})</span>}
        </dd>
        <dt>First seen</dt>
        <dd>{when(detection.temporal_bounds_start)}</dd>
        <dt>Last seen</dt>
        <dd>{when(detection.last_detected_at)}</dd>
        <dt>Position</dt>
        <dd>
          {typeof detection.latitude === "number" && typeof detection.longitude === "number"
            ? `${detection.latitude.toFixed(4)}, ${detection.longitude.toFixed(4)}`
            : "not on the map — this rule is about identity, not place"}
        </dd>
        <dt>Rule</dt>
        <dd>
          <code>{gate ?? "—"}</code>
        </dd>
      </dl>
    </aside>
  );
}
