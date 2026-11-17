// Deliverable 2a — what the spoofing detector does, for someone who has never
// read the code.
//
// This is static content on purpose. It describes the detector's design, not
// its current output, so it must not change when the sky is quiet. The rules
// listed here are the ones in air/detectors/spoofing/: if a rule is added or
// retired, update GATES below and the summary line with it.
import { useState } from "react";

interface Rule {
  gate: string;
  name: string;
  question: string;
  branch: "physics" | "identity";
}

// Ordered as the detector runs them: the physics rules compare consecutive
// reports, the identity rules ask whether the aircraft is who it claims.
const GATES: Rule[] = [
  {
    gate: "speed_delta_v1",
    name: "Speed disagreement",
    branch: "physics",
    question:
      "The aircraft says how fast it is going, and its positions say how far it moved. Those two should agree. When they do not, one of them is wrong.",
  },
  {
    gate: "turn_rate_v1",
    name: "Impossible turn",
    branch: "physics",
    question:
      "How fast the aircraft's heading changed, against what the airframe can physically sustain at that speed. A jet cannot pivot like a drone.",
  },
  {
    gate: "vrate_delta_v1",
    name: "Climb rate disagreement",
    branch: "physics",
    question:
      "The reported vertical speed against the altitude actually gained or lost. Accounts for the fact that altitude is reported in steps of 25 or 100 feet.",
  },
  {
    gate: "teleport_v1",
    name: "Teleport",
    branch: "physics",
    question:
      "A jump between two positions faster than any aircraft can fly. The bluntest check we have, and the hardest to argue with.",
  },
  {
    gate: "subterrain_v1",
    name: "Below the ground",
    branch: "physics",
    question:
      "A reported position underneath the terrain beneath it. Either the altitude or the position is false; an aircraft cannot be inside a hill.",
  },
  {
    gate: "nic_floor_v1",
    name: "Navigation integrity collapse",
    branch: "physics",
    question:
      "Aircraft broadcast how much they trust their own GPS fix. Under jamming that number collapses and stays down. Brief dips are normal equipment behaviour, so we require it to hold.",
  },
  {
    gate: "identity_drift_v1",
    name: "Callsign drift",
    branch: "identity",
    question:
      "One address broadcasting a different callsign. A change within one airline is the crew entering their next flight, so only a change of operator counts.",
  },
  {
    gate: "coexistence_v1",
    name: "Two places at once",
    branch: "identity",
    question:
      "One identity reported from two places it could not have travelled between. Two transmitters are claiming the same aircraft.",
  },
  {
    gate: "pingpong_v1",
    name: "Position ping-pong",
    branch: "identity",
    question:
      "The position alternating between two places, each hop impossible. The signature of two transmitters sharing an address rather than one bad fix.",
  },
  {
    gate: "reappear_v1",
    name: "Impossible reappearance",
    branch: "identity",
    question:
      "An aircraft that went quiet and came back further away than it could have flown while silent.",
  },
  {
    gate: "registry_mismatch_v1",
    name: "Registry mismatch",
    branch: "identity",
    question:
      "Performance that contradicts the registered aircraft — a Cessna's address reporting airliner speeds at airliner altitudes.",
  },
];

export function AlgorithmPanel() {
  const [open, setOpen] = useState(false);

  return (
    <section className="algo">
      <h2>How this detector works</h2>

      <p className="algo-lead">
        ADS-B is unauthenticated: an aircraft simply broadcasts who it is and where
        it is, and anyone can transmit the same thing. There is no signature to
        check, so we cannot ask whether a message is genuine. We ask instead
        whether it is <em>consistent</em> — with the message before it, and with
        what an aircraft can physically do.
      </p>

      <div className="algo-branches">
        <div className="algo-branch">
          <h3>Physics</h3>
          <p>
            Every message carries both a claimed <strong>state</strong> (speed,
            track, climb rate) and a claimed <strong>position</strong>. Each is
            checked against the other across consecutive reports. A spoofer has to
            keep both stories straight at once, and small errors compound.
          </p>
        </div>
        <div className="algo-branch">
          <h3>Identity</h3>
          <p>
            Separately, we ask whether the aircraft is who it says. One address in
            two places, a callsign that changes operator mid-flight, performance
            that does not match the registered airframe.
          </p>
        </div>
      </div>

      <h3>What we do about uncertainty</h3>
      <ul className="algo-points">
        <li>
          <strong>Abstain rather than guess.</strong> A missing position is not
          (0,&nbsp;0). A report we cannot use is skipped, never filled in.
        </li>
        <li>
          <strong>Allow for honest error.</strong> Every threshold accounts for
          the position error the aircraft itself declares, plus timing slop.
          Being wrong about a limit is how a detector invents alerts.
        </li>
        <li>
          <strong>One finding per episode.</strong> A rule that trips for thirty
          seconds is one alert, not thirty.
        </li>
        <li>
          <strong>Confidence is about the deviation, not the threat.</strong> We
          report how sure we are that two things disagree. Whether that is an
          attack is someone else's judgement.
        </li>
      </ul>

      <button className="btn ghost algo-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "Hide the rules" : `Show all ${GATES.length} rules`}
      </button>

      {open && (
        <table className="algo-table">
          <thead>
            <tr>
              <th>Rule</th>
              <th>Branch</th>
              <th>What it asks</th>
            </tr>
          </thead>
          <tbody>
            {GATES.map((r) => (
              <tr key={r.gate}>
                <td>
                  <div className="algo-name">{r.name}</div>
                  <code className="algo-gate">{r.gate}</code>
                </td>
                <td>
                  <span className={`algo-pill ${r.branch}`}>{r.branch}</span>
                </td>
                <td className="algo-q">{r.question}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

export const SPOOFING_GATES = GATES;
