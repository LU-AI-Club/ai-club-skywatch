// "Is this detector alive, or is the sky just quiet?"
//
// Those two states look identical on a dashboard -- an empty table either way.
// Proximity sits in the quiet one most of the time by design: the thresholds
// are strict and real conflicts are rare, so without this line a working
// detector reads as a broken one.
//
// The run heartbeat answers it. Every tick writes a detector_runs row whether
// or not it found anything, so a recent SUCCESS with a non-zero observation
// count is evidence the pipeline ran AND had data to look at.
import { useEffect, useState } from "react";
import { useDetectorRuns } from "../api/hooks";
import type { DetectorRun } from "../api/types";

const DETECTOR_ID = "skywatch.proximity";
const STALE_AFTER_MS = 120_000;
// Re-read the heartbeat on this cadence. The proximity runner ticks every 30 s,
// so this sees two or three ticks before STALE_AFTER_MS could ever elapse.
const REFRESH_MS = 15_000;

function formatElapsed(ms: number): string {
  if (ms < 0) return "just now";

  const seconds = Math.floor(ms / 1000);

  if (seconds < 60) return `${seconds} seconds ago`;

  const minutes = Math.floor(seconds / 60);

  if (minutes < 60) {
    return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  }

  const hours = Math.floor(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

function getCount(
  counts: Record<string, unknown>,
  key: string
): number {
  const value = Number(counts[key]);
  return Number.isFinite(value) ? value : 0;
}

export default function DetectorHealth() {
  const { data, loading, error, reload } = useDetectorRuns({
    detector_id: DETECTOR_ID,
    limit: 5,
  });

  // Two different clocks. The 1 s tick re-renders so "12 seconds ago" counts
  // up smoothly; the slower one re-reads the heartbeat. Without the re-read
  // the counts freeze at page load and the line declares itself STALE after
  // two minutes while the detector is running perfectly well.
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    const refetch = window.setInterval(reload, REFRESH_MS);
    return () => {
      window.clearInterval(tick);
      window.clearInterval(refetch);
    };
  }, [reload]);

  if (loading && !data) {
    return <div className="detector-health">Checking detector status...</div>;
  }

  if (error && !data) {
    return (
      <div className="detector-health detector-health--error">
        Unable to retrieve detector health: {error}
      </div>
    );
  }

  // Skip a tick that is still in flight: RUNNING rows have no counts yet, so
  // taking one would flash "Found 0 detections" between every refresh.
  const runs = (data ?? []).filter(
    (run) => run.detector_id === DETECTOR_ID && run.status !== "RUNNING"
  );

  const latestRun: DetectorRun | undefined = runs.sort(
    (a, b) =>
      new Date(b.completed_at ?? b.started_at).getTime() -
      new Date(a.completed_at ?? a.started_at).getTime()
  )[0];

  if (!latestRun) {
    return (
      <div className="detector-health detector-health--error">
        Proximity detector: No runs recorded
      </div>
    );
  }

  const timestamp = latestRun.completed_at ?? latestRun.started_at;
  const runTime = new Date(timestamp).getTime();

  const isStale =
    !Number.isFinite(runTime) || now - runTime > STALE_AFTER_MS;

  const isFailed = latestRun.status === "FAILED";
  const isUnhealthy = isFailed || isStale;

  const observations = getCount(latestRun.counts, "observations");
  const detections = getCount(latestRun.counts, "detections");

  const status = isFailed
    ? "FAILED"
    : isStale
      ? "STALE"
      : latestRun.status;

  return (
    <div
      className={`detector-health ${
        isUnhealthy ? "detector-health--error" : ""
      }`}
      role="status"
      aria-live="polite"
    >
      <span>
        Proximity detector last ran{" "}
        {formatElapsed(now - runTime)}
      </span>

      <span className="detector-health__status">
        {status}
      </span>

      <span>
        Scanned {observations.toLocaleString()} aircraft
      </span>

      <span>
        Found {detections.toLocaleString()} detections
      </span>

      {isFailed && latestRun.error ? (
        <span className="detector-health__error">{latestRun.error}</span>
      ) : null}
    </div>
  );
}
