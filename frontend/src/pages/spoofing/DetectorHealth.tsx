// Deliverable 2c — is the detector alive?
//
// The problem this solves: a page showing no detections is ambiguous. A quiet
// sky and a dead runner look exactly the same, and the quiet sky is the normal
// case — we average a handful of findings an hour. Without this, every empty
// table reads as "broken" and every real outage reads as "quiet".
//
// The runner writes a row to detector_runs every tick with its status and
// counts, so "when did it last run, and what did it see" is answerable.
import { useDetectorRuns } from "../../api/hooks";
import type { DetectorRun } from "../../api/types";

const DETECTOR_ID = "skywatch.spoofing";

// The runner's own interval (scripts/run_live_detector.py: poll_interval_s for
// spoofing). Two missed ticks is the line between "between runs" and "stopped"
// -- one is ordinary jitter, two is not.
const TICK_S = 300;
const STALE_S = TICK_S * 2;

function agoSeconds(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : (Date.now() - t) / 1000;
}

function humanAgo(seconds: number): string {
  if (seconds < 90) return `${Math.round(seconds)}s ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} min ago`;
  return `${Math.round(seconds / 3600)} h ago`;
}

function countOf(run: DetectorRun, key: string): number | null {
  const v = run.counts?.[key];
  return typeof v === "number" ? v : null;
}

type Health =
  | { state: "ok"; label: string }
  | { state: "warn"; label: string }
  | { state: "bad"; label: string };

function assess(run: DetectorRun | undefined, loading: boolean, error: string | null): Health {
  if (loading) return { state: "warn", label: "Checking…" };
  if (error) return { state: "bad", label: "Can't reach the API" };
  if (!run) return { state: "bad", label: "Never run" };

  // A failed tick is worth saying plainly even if a later one succeeded: the
  // runner survives a bad tick on purpose, so failures are quiet by design.
  if (run.status === "FAILED") return { state: "bad", label: "Last run failed" };

  const age = agoSeconds(run.completed_at ?? run.started_at);
  if (age === null) return { state: "warn", label: "Ran, time unknown" };
  if (run.status === "RUNNING") return { state: "ok", label: "Running now" };
  if (age > STALE_S) return { state: "bad", label: `No run for ${humanAgo(age)}` };
  return { state: "ok", label: `Ran ${humanAgo(age)}` };
}

export function DetectorHealth() {
  // limit 5 rather than 1: one FAILED tick between two successes is a
  // different story from a detector that is simply down, and the only way to
  // see it is to look at more than the newest row.
  const { data, loading, error } = useDetectorRuns({
    detector_id: DETECTOR_ID,
    limit: 5,
  });

  const runs = data ?? [];
  const latest = runs[0];
  const health = assess(latest, loading, error);
  const recentFailures = runs.filter((r) => r.status === "FAILED").length;

  const observations = latest ? countOf(latest, "observations") : null;
  const detections = latest ? countOf(latest, "detections") : null;

  return (
    <section className={`health health-${health.state}`}>
      <div className="health-row">
        <span className={`health-dot ${health.state}`} aria-hidden="true" />
        <strong className="health-label">{health.label}</strong>
        {latest && (
          <span className="health-detail">
            {observations !== null && detections !== null ? (
              <>
                read {observations.toLocaleString()} observation
                {observations === 1 ? "" : "s"}, found {detections}
              </>
            ) : (
              <>status {latest.status}</>
            )}
          </span>
        )}
      </div>

      {/* The whole point of this panel, said out loud rather than implied. */}
      {health.state === "ok" && detections === 0 && (
        <p className="health-note">
          Nothing found on the last run. That is the normal state — most of the
          time nothing is spoofing. An empty table below means working, not broken.
        </p>
      )}

      {health.state === "bad" && (
        <p className="health-note">
          Detections below may be stale. Check the runner:{" "}
          <code>docker logs --tail 20 skywatch-spoofing-runner</code>
        </p>
      )}

      {recentFailures > 0 && health.state !== "bad" && (
        <p className="health-note">
          {recentFailures} of the last {runs.length} runs failed. The runner keeps
          going after a bad tick, so this would otherwise be invisible.
        </p>
      )}
    </section>
  );
}
