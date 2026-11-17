// Deliverable 2b — the findings themselves.
//
// Our own table rather than the shared DetectionTable, which says in its own
// comment that teams are expected to replace it. Two reasons we do:
//
//   - It shows `detection_type` ("kinematic_inconsistency"), which is the same
//     string for four of our rules. The useful column is which *rule* fired,
//     and that lives in metadata.gate.
//   - Rows need to be clickable so the detail panel can open, and adding that
//     to the shared component would mean editing a file all three teams use.
import type { Detection } from "../../api/types";
import { SeverityBadge } from "../../components/SeverityBadge";
import { SPOOFING_GATES } from "./AlgorithmPanel";

const NAMES = new Map(SPOOFING_GATES.map((g) => [g.gate, g.name]));

function meta(d: Detection): Record<string, unknown> {
  const m = d.metadata;
  return m && typeof m === "object" ? (m as Record<string, unknown>) : {};
}

function ruleOf(d: Detection): string {
  const g = meta(d).gate;
  if (typeof g === "string") return NAMES.get(g) ?? g;
  return d.detection_type ?? "—";
}

// "72.4 / 52.4 kt" — what was measured against the limit it broke. The single
// most informative thing we can put in a row, and no other detector has it.
function measurement(d: Detection): string {
  const event = meta(d).event;
  if (!event || typeof event !== "object") return "—";
  const e = event as Record<string, unknown>;
  const measured = typeof e.measured === "number" ? e.measured : null;
  const threshold = typeof e.threshold === "number" ? e.threshold : null;
  const unit = typeof e.unit === "string" ? e.unit : "";
  if (measured === null || threshold === null) return "—";
  return `${measured.toFixed(1)} / ${threshold.toFixed(1)} ${unit}`.trim();
}

function shortTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString();
}

export function FindingsTable({
  detections,
  selectedId,
  onSelect,
}: {
  detections: Detection[];
  selectedId: string | null;
  onSelect: (d: Detection) => void;
}) {
  return (
    <table className="table findings-table">
      <thead>
        <tr>
          <th>Severity</th>
          <th>Rule</th>
          <th>Aircraft</th>
          <th>Measured / limit</th>
          <th>Confidence</th>
          <th>Last seen</th>
        </tr>
      </thead>
      <tbody>
        {detections.map((d) => (
          <tr
            key={d.detection_id}
            className={`row-click ${selectedId === d.detection_id ? "on" : ""}`}
            onClick={() => onSelect(d)}
            // Keyboard reachable: a row that only responds to a mouse is
            // unusable for anyone tabbing through the page.
            tabIndex={0}
            role="button"
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(d);
              }
            }}
          >
            <td>
              <SeverityBadge severity={d.severity} />
            </td>
            <td>{ruleOf(d)}</td>
            <td>
              <code>{d.entity_id}</code>
            </td>
            <td className="num">{measurement(d)}</td>
            <td className="num">
              {typeof d.confidence === "number" ? d.confidence.toFixed(2) : "—"}
            </td>
            <td>{shortTime(d.last_detected_at)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
