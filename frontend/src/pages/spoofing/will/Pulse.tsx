// The detector's vital signs, as a single strip across the top.
//
// Same job as a status badge, said differently: rather than "last ran 2 min
// ago", this shows the last few runs as a row of ticks you can read at a
// glance — how recent, how big, whether any failed. A detector that stopped
// three runs ago is obvious here in a way a single timestamp never is.
import { useDetectorRuns } from "../../../api/hooks";
import type { DetectorRun } from "../../../api/types";

const DETECTOR_ID = "skywatch.spoofing";
const TICK_S = 300; // the runner's own interval
const RUNS = 12;

function ageSeconds(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : (Date.now() - t) / 1000;
}

function ago(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)}s`;
  if (seconds < 5400) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

function count(run: DetectorRun, key: string): number | null {
  const v = run.counts?.[key];
  return typeof v === "number" ? v : null;
}

export function Pulse({ findings }: { findings: number }) {
  const { data, loading, error } = useDetectorRuns({
    detector_id: DETECTOR_ID,
    limit: RUNS,
  });

  const runs = data ?? [];
  const latest = runs[0];
  const age = latest ? ageSeconds(latest.completed_at ?? latest.started_at) : null;
  // Two missed ticks, not one: a single late run is ordinary jitter.
  const stale = age !== null && age > TICK_S * 2;
  const dead = !!error || (!loading && !latest) || stale || latest?.status === "FAILED";

  const observations = latest ? count(latest, "observations") : null;
  const biggest = runs.reduce((n, r) => Math.max(n, count(r, "observations") ?? 0), 0);

  return (
    <div className={`wpulse ${dead ? "down" : "up"}`}>
      <div className="wpulse-state">
        <span className={`wpulse-dot ${dead ? "down" : "up"}`} />
        <span className="wpulse-word">{dead ? "not running" : "watching"}</span>
      </div>

      {/* One tick per run, newest on the right. Height is how much data that
          run read, so a run that saw nothing is visibly short rather than
          silently absent. */}
      <div className="wpulse-ticks" aria-hidden="true">
        {[...runs].reverse().map((r) => {
          const obs = count(r, "observations") ?? 0;
          const h = biggest > 0 ? Math.max(8, (obs / biggest) * 100) : 8;
          const found = (count(r, "detections") ?? 0) > 0;
          return (
            <span
              key={r.detection_run_id}
              className={`wtick ${r.status === "FAILED" ? "bad" : found ? "hit" : ""}`}
              style={{ height: `${h}%` }}
              title={`${r.status} · ${obs.toLocaleString()} observations · ${
                count(r, "detections") ?? 0
              } found`}
            />
          );
        })}
      </div>

      <dl className="wpulse-stats">
        <div>
          <dt>last run</dt>
          <dd>{loading ? "…" : age === null ? "never" : ago(age)}</dd>
        </div>
        <div>
          <dt>reading</dt>
          <dd>{observations === null ? "—" : observations.toLocaleString()}</dd>
        </div>
        <div>
          <dt>findings</dt>
          <dd>{findings}</dd>
        </div>
      </dl>

      {/* The sentence that stops an empty page reading as a broken one. */}
      {!dead && findings === 0 && !loading && (
        <p className="wpulse-note">
          Nothing disagreeing with itself right now. That is the normal state.
        </p>
      )}
      {dead && (
        <p className="wpulse-note bad">
          {error
            ? `API unreachable — ${error}`
            : "No recent run. Anything below may be stale."}
        </p>
      )}
    </div>
  );
}
