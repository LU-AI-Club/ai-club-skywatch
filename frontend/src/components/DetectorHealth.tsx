
import { useEffect, useState } from "react";
import { useDetectorRuns } from "../api/hooks";
import type { DetectorRun } from "../api/types";

const DETECTOR_ID = "skywatch.proximity";
const STALE_AFTER_MS = 120_000;

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
  const { data, loading, error } = useDetectorRuns({
    detector_id: DETECTOR_ID,
  });

  // Update elapsed time every second.
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => {
      setNow(Date.now());
    }, 1000);

    return () => window.clearInterval(interval);
  }, []);

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

  const runs = (data ?? []).filter(
    (run) => run.detector_id === DETECTOR_ID
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
    </div>
  );
}
