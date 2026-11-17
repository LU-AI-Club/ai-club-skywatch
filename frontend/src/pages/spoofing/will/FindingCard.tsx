// One finding, as the disagreement it actually is.
//
// A row in a table tells you something fired. This tells you what the argument
// was: the aircraft said one number, its own positions said another, and here
// is the gap. Two opposed bars on a shared scale, so the size of the
// disagreement is visible before you read a single digit.
//
// Identity findings have no such pair, so they get a different body rather
// than an empty chart. Forcing one shape onto both would make the identity
// rules look broken.
import { useState } from "react";
import type { Detection } from "../../../api/types";
import { claimOf, factsOf, gateOf, limitsOf, measurementOf } from "./claim";

const RULE_NAMES: Record<string, string> = {
  speed_delta_v1: "Speed",
  turn_rate_v1: "Turn rate",
  vrate_delta_v1: "Climb rate",
  nic_floor_v1: "GPS integrity",
  identity_drift_v1: "Callsign",
  teleport_v1: "Teleport",
  subterrain_v1: "Below ground",
  coexistence_v1: "Two places at once",
  pingpong_v1: "Position ping-pong",
  reappear_v1: "Reappearance",
  registry_mismatch_v1: "Registry",
};

function sevClass(d: Detection): string {
  return `sev-${String(d.severity ?? "low").toLowerCase()}`;
}

function clockTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso);
  return Number.isNaN(t.getTime()) ? "—" : t.toLocaleTimeString([], { hour12: false });
}

export function FindingCard({ detection }: { detection: Detection }) {
  const [open, setOpen] = useState(false);
  const gate = gateOf(detection);
  const claim = claimOf(detection);
  const measurement = measurementOf(detection);
  const facts = factsOf(detection);
  const limits = limitsOf(detection);

  // Both bars share one scale so their lengths are comparable. Without this
  // each would fill its own track and a 2x disagreement would look identical
  // to a 10x one.
  const scale = claim ? Math.max(claim.claimed, claim.actual) : 0;
  const pct = (v: number) => (scale > 0 ? Math.max(2, (v / scale) * 100) : 0);

  return (
    <article className={`wcard ${sevClass(detection)} ${open ? "open" : ""}`}>
      <header className="wcard-top">
        <span className="wcard-rule">{RULE_NAMES[gate] ?? gate}</span>
        <code className="wcard-ac">{String(detection.entity_id).replace("aircraft:", "")}</code>
        <span className="wcard-time">{clockTime(detection.last_detected_at)}</span>
        <span className={`wcard-sev ${sevClass(detection)}`}>{detection.severity}</span>
      </header>

      {claim ? (
        <div className="wclaim">
          <div className="wclaim-row">
            <span className="wclaim-label">said</span>
            <span className="wclaim-track">
              <span className="wclaim-bar said" style={{ width: `${pct(claim.claimed)}%` }} />
            </span>
            <span className="wclaim-num">
              {Math.round(claim.claimed)}
              <small>{claim.unit}</small>
            </span>
          </div>

          <div className="wclaim-row">
            <span className="wclaim-label">did</span>
            <span className="wclaim-track">
              <span className="wclaim-bar did" style={{ width: `${pct(claim.actual)}%` }} />
            </span>
            <span className="wclaim-num">
              {Math.round(claim.actual)}
              <small>{claim.unit}</small>
            </span>
          </div>

          <p className="wclaim-gap">
            {Number.isFinite(claim.ratio) ? (
              <>
                <strong>{claim.ratio.toFixed(1)}×</strong> what it claimed
              </>
            ) : (
              <>claimed a standstill while moving</>
            )}
            {claim.dtSeconds !== null && claim.distanceM !== null && (
              <span className="muted">
                {" "}
                · {(claim.distanceM / 1852).toFixed(2)} nm in {claim.dtSeconds.toFixed(1)} s
              </span>
            )}
          </p>
        </div>
      ) : measurement ? (
        // Every other rule: its own measured quantity against its own limit.
        // Same two-bar shape, different question -- "how far past the line"
        // rather than "how far from what it claimed".
        <div className="wclaim">
          <div className="wclaim-row">
            <span className="wclaim-label">limit</span>
            <span className="wclaim-track">
              <span
                className="wclaim-bar said"
                style={{
                  width: `${Math.max(
                    2,
                    (Math.abs(measurement.threshold) /
                      Math.max(Math.abs(measurement.measured), Math.abs(measurement.threshold))) *
                      100,
                  )}%`,
                }}
              />
            </span>
            <span className="wclaim-num">
              {Math.abs(measurement.threshold) < 10
                ? measurement.threshold.toFixed(1)
                : Math.round(measurement.threshold)}
              <small>{measurement.unit}</small>
            </span>
          </div>

          <div className="wclaim-row">
            <span className="wclaim-label">actual</span>
            <span className="wclaim-track">
              <span
                className="wclaim-bar did"
                style={{
                  width: `${Math.max(
                    2,
                    (Math.abs(measurement.measured) /
                      Math.max(Math.abs(measurement.measured), Math.abs(measurement.threshold))) *
                      100,
                  )}%`,
                }}
              />
            </span>
            <span className="wclaim-num">
              {Math.abs(measurement.measured) < 10
                ? measurement.measured.toFixed(1)
                : Math.round(measurement.measured)}
              <small>{measurement.unit}</small>
            </span>
          </div>

          <p className="wclaim-gap">
            <strong>
              {measurement.overPercent < 1
                ? `${measurement.overPercent.toFixed(2)}%`
                : `${measurement.overPercent.toFixed(0)}%`}
            </strong>{" "}
            past the limit
          </p>
        </div>
      ) : (
        // Nothing measurable — the identity rules. Say what the finding is
        // rather than showing an empty chart.
        <div className="wclaim wclaim-none">
          <p>{facts[0] ?? "No measurable quantity for this rule."}</p>
        </div>
      )}

      <footer className="wcard-foot">
        <span className="wconf" title="Detector confidence">
          <span className="wconf-track">
            <span
              className="wconf-fill"
              style={{ width: `${Math.round((detection.confidence ?? 0) * 100)}%` }}
            />
          </span>
          {typeof detection.confidence === "number" ? detection.confidence.toFixed(2) : "—"}
        </span>

        {measurement && measurement.overPercent < 1 && (
          // Worth saying on the card, not buried in the detail: this one only
          // just crossed its line.
          <span className="wthin">barely over the line</span>
        )}

        <button className="wmore" onClick={() => setOpen((v) => !v)}>
          {open ? "less" : "why"}
        </button>
      </footer>

      {open && (
        <div className="wdetail">
          {measurement && (
            <p className="wdetail-measure">
              measured <strong>{measurement.measured.toFixed(1)}</strong> against a limit of{" "}
              <strong>{measurement.threshold.toFixed(1)}</strong> {measurement.unit}
              {" — "}
              {measurement.overPercent < 1
                ? `${measurement.overPercent.toFixed(2)}% over`
                : `${measurement.overPercent.toFixed(0)}% over`}
            </p>
          )}

          {facts.length > 0 && (
            <ul className="wdetail-facts">
              {facts.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
            </ul>
          )}

          {limits.length > 0 && (
            <>
              <h4>what this does not tell you</h4>
              <ul className="wdetail-limits">
                {limits.map((l, i) => (
                  <li key={i}>{l}</li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </article>
  );
}
