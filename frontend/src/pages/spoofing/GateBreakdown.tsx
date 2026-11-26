// Deliverable 2b — detections gathered, broken down by which rule found them.
//
// A total alone ("51 detections") says nothing about what is happening. Eleven
// speed disagreements and one callsign drift is a very different sky from
// eleven callsign drifts, and the rule name is the shortest route to that.
//
// Counts come from GET /spoofing-gates rather than being tallied from the
// fetched rows, for one reason: the detection list is capped by `limit`, so
// counting it would quietly undercount whenever there are more findings than
// the page asked for. The endpoint counts in the database and returns a zero
// for every rule that is live but quiet, which an empty list cannot express.
import { useSpoofingGates } from "../../api/hooks";
import { SPOOFING_GATES } from "./AlgorithmPanel";

const NAMES = new Map(SPOOFING_GATES.map((g) => [g.gate, g.name]));
const BRANCH = new Map(SPOOFING_GATES.map((g) => [g.gate, g.branch]));

export function GateBreakdown({
  sinceHours,
  selected,
  onSelect,
}: {
  sinceHours: number;
  selected: string | null;
  onSelect: (gate: string | null) => void;
}) {
  const { data, loading, error } = useSpoofingGates({ since_hours: sinceHours });
  const rows = data ?? [];
  const total = rows.reduce((n, r) => n + r.count, 0);
  const max = rows.reduce((n, r) => Math.max(n, r.count), 0);

  if (error) {
    return <p className="muted">Rule breakdown unavailable: {error}</p>;
  }

  const firing = rows.filter((r) => r.count > 0);
  const quiet = rows.filter((r) => r.count === 0);

  return (
    <section className="gates">
      <div className="gates-head">
        <h2>Which rules fired</h2>
        <span className="muted">
          {loading ? "…" : `${total} finding${total === 1 ? "" : "s"} in ${sinceHours}h`}
        </span>
      </div>

      {!loading && firing.length === 0 && (
        <p className="muted">No rule fired in this window.</p>
      )}

      <ul className="gate-list">
        {firing.map((r) => {
          const isOn = selected === r.gate;
          return (
            <li key={r.gate}>
              <button
                className={`gate-row ${isOn ? "on" : ""}`}
                onClick={() => onSelect(isOn ? null : r.gate)}
                title={isOn ? "Show all rules" : `Show only ${r.gate}`}
              >
                <span className="gate-name">
                  {NAMES.get(r.gate) ?? r.gate}
                  <span className={`algo-pill ${BRANCH.get(r.gate) ?? ""}`}>
                    {BRANCH.get(r.gate) ?? "rule"}
                  </span>
                </span>
                <span className="gate-bar">
                  <span
                    className="gate-fill"
                    style={{ width: max ? `${(r.count / max) * 100}%` : "0%" }}
                  />
                </span>
                <span className="gate-count">{r.count}</span>
              </button>
            </li>
          );
        })}
      </ul>

      {/* Rules that found nothing are listed too. "This rule is watching and
          saw nothing" is information; leaving them out would make a quiet rule
          indistinguishable from one that does not exist. */}
      {quiet.length > 0 && (
        <p className="gates-quiet">
          <span className="muted">Watching, nothing found: </span>
          {quiet.map((r, i) => (
            <span key={r.gate}>
              {i > 0 && ", "}
              <span title={r.gate}>{NAMES.get(r.gate) ?? r.gate}</span>
            </span>
          ))}
        </p>
      )}
    </section>
  );
}
