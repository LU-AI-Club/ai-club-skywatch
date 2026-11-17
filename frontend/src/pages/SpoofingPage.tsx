// Spoofing — Will's dashboard.
//
// Built around one idea: every finding this detector produces is a
// disagreement between what an aircraft *said* about itself and what its own
// positions *did*. So the page leads with that pair rather than with a table.
// A row of counts tells you something fired; two opposed bars tell you how
// badly the story failed to add up, before you read a digit.
//
// Three deliverables, arranged to match how someone actually reads the page:
//   detector health  -> the pulse strip, first, so empty is never ambiguous
//   detections       -> the cards, which are the page
//   algorithm        -> folded away at the bottom, reference rather than news
import { useMemo, useState } from "react";
import { useSpoofingDetections, useSpoofingGates } from "../api/hooks";
import type { Detection } from "../api/types";
import { FindingCard } from "./spoofing/will/FindingCard";
import { Pulse } from "./spoofing/will/Pulse";
import { gateOf } from "./spoofing/will/claim";
import "./spoofing/will/will.css";

const RANGES = [
  { hours: 1, label: "1h" },
  { hours: 6, label: "6h" },
  { hours: 24, label: "24h" },
  { hours: 168, label: "7d" },
] as const;

const SHORT: Record<string, string> = {
  speed_delta_v1: "Speed",
  turn_rate_v1: "Turn",
  vrate_delta_v1: "Climb",
  nic_floor_v1: "GPS",
  identity_drift_v1: "Callsign",
  teleport_v1: "Teleport",
  subterrain_v1: "Terrain",
  coexistence_v1: "Duplicate",
  pingpong_v1: "Ping-pong",
  reappear_v1: "Reappear",
  registry_mismatch_v1: "Registry",
};

const SEVERITY_ORDER: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3 };

export function SpoofingPage() {
  const [hours, setHours] = useState<number>(24);
  const [gate, setGate] = useState<string | null>(null);

  // `gate` is our own filter — it reaches into metadata, which the shared
  // endpoint cannot do. See api/main.py.
  const { data, loading, error, reload } = useSpoofingDetections({
    since_hours: hours,
    gate: gate ?? undefined,
  });
  const counts = useSpoofingGates({ since_hours: hours });

  // Worst first. A page you scan top-left to bottom-right should put the thing
  // that matters where the eye lands, not wherever the database happened to
  // order it.
  const findings: Detection[] = useMemo(() => {
    const rows = data ?? [];
    return [...rows].sort((a, b) => {
      const sa = SEVERITY_ORDER[String(a.severity).toLowerCase()] ?? 9;
      const sb = SEVERITY_ORDER[String(b.severity).toLowerCase()] ?? 9;
      if (sa !== sb) return sa - sb;
      return (b.confidence ?? 0) - (a.confidence ?? 0);
    });
  }, [data]);

  const firing = (counts.data ?? []).filter((g) => g.count > 0);
  const quiet = (counts.data ?? []).filter((g) => g.count === 0);

  return (
    <div className="page wpage">
      <header className="wmast">
        <div>
          <h1>Spoofing</h1>
          <p>
            Aircraft broadcast who they are and where they are, and nobody signs
            it. We cannot ask whether a message is genuine — only whether the
            story holds together.
          </p>
        </div>
      </header>

      <Pulse findings={findings.length} />

      <div className="wbar">
        {RANGES.map((r) => (
          <button
            key={r.hours}
            className={`wchip ${hours === r.hours ? "on" : ""}`}
            onClick={() => setHours(r.hours)}
          >
            {r.label}
          </button>
        ))}

        <span className="wbar-sep" />

        <button className={`wchip ${gate === null ? "on" : ""}`} onClick={() => setGate(null)}>
          All
        </button>
        {firing.map((g) => (
          <button
            key={g.gate}
            className={`wchip ${gate === g.gate ? "on" : ""}`}
            onClick={() => setGate(gate === g.gate ? null : g.gate)}
            title={g.gate}
          >
            {SHORT[g.gate] ?? g.gate}
            <span className="n">{g.count}</span>
          </button>
        ))}

        <span className="wbar-right">
          <button className="wchip" onClick={reload} disabled={loading}>
            {loading ? "…" : "Refresh"}
          </button>
        </span>
      </div>

      {error && <div className="wempty">Couldn't reach the API — {error}</div>}

      {!loading && !error && findings.length === 0 ? (
        <div className="wempty">
          Nothing disagreed with itself in the last {hours < 24 ? `${hours}h` : `${hours / 24}d`}.
        </div>
      ) : (
        <div className="wgrid">
          {findings.map((d) => (
            <FindingCard key={d.detection_id} detection={d} />
          ))}
        </div>
      )}

      {/* Rules that are watching and found nothing. Worth naming: otherwise a
          quiet rule is indistinguishable from one that does not exist. */}
      {quiet.length > 0 && !loading && (
        <p className="wpulse-note" style={{ marginTop: 16 }}>
          Also watching, nothing found:{" "}
          {quiet.map((g) => SHORT[g.gate] ?? g.gate).join(" · ")}
        </p>
      )}

      <details className="wexplain">
        <summary>How this detector decides</summary>
        <div className="wexplain-body">
          <p>
            Every message carries two stories. One is what the aircraft{" "}
            <strong>says</strong> about itself — its speed, its heading, how fast
            it is climbing. The other is what its <strong>positions</strong> show
            it actually did between one report and the next. A real aircraft
            tells the same story twice. A spoofer has to keep both straight, and
            small errors compound.
          </p>
          <p>
            That is what the bars above are. The grey bar is the claim; the amber
            bar is the measurement. When they match, there is nothing to see —
            which is most of the time, on most aircraft.
          </p>
          <p>
            A second set of rules asks a different question:{" "}
            <strong>is this aircraft who it says it is?</strong> One address
            reported from two places at once. A callsign that changes to another
            airline mid-flight. Performance that contradicts the registered
            airframe. Those have no two numbers to compare, so their cards show
            the finding in words instead.
          </p>
          <p>
            Every limit allows for honest error — the position error the aircraft
            itself declares, plus timing slop — because being wrong about a limit
            is how a detector invents alerts. When a reading cannot be used, it
            is skipped rather than guessed at. And confidence here is about{" "}
            <strong>the deviation, not the threat</strong>: we report how sure we
            are that two things disagree. Whether that is an attack is someone
            else's call.
          </p>
        </div>
      </details>
    </div>
  );
}
