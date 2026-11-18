// Page header: NOTAM line, title, detector status, feed warning, Zulu clock,
// and the alerts / shortcuts buttons.
import type { DetectorRun } from "../../../api/types";
import { ago, zuluClock, zuluDay } from "../format";
import { useNow } from "../hooks/useNow";
import type { FeedHealth } from "../hooks/useFeedHealth";

function DetectorStatus({ runs, error }: { runs: DetectorRun[] | null; error: string | null }) {
  const last = runs?.[0];
  let text: string;
  let color = "var(--muted)";
  if (error) {
    text = `Couldn't check detector status: ${error}`;
    color = "var(--sev-critical)";
  } else if (!runs) {
    text = "Checking detector status…";
  } else if (!last) {
    text = "No detector runs recorded — the detector may never have run.";
    color = "var(--sev-high)";
  } else {
    const found = last.counts?.detections ?? last.counts?.emitted ?? last.counts?.found;
    const status = last.status.toUpperCase();
    color = status === "SUCCESS" ? "var(--sev-low)" : status === "FAILED" ? "var(--sev-critical)" : "var(--sev-medium)";
    text =
      `Detector last ran ${ago(last.completed_at ?? last.started_at)} · ${status}` +
      (found !== undefined ? ` · found ${String(found)}` : "") +
      (last.error ? ` · ${last.error}` : "");
  }
  const live = !error && !!last && last.status.toUpperCase() !== "FAILED";
  return (
    <div className="nfz-status">
      <span className={`nfz-dot${live ? " nfz-dot--live" : ""}`} style={{ background: color, color }} />
      {text}
    </div>
  );
}

function ZuluClock() {
  const now = useNow(1000);
  return (
    <div className="nfz-clock" aria-label="Current UTC time">
      <span className="nfz-clock-time">{zuluClock(now)}</span>
      <span className="nfz-clock-date">
        {zuluDay(now)} {new Date(now).getUTCFullYear()} · UTC
      </span>
    </div>
  );
}

export function Header({
  runs,
  runsError,
  health,
  alertsOn,
  alertsBlocked,
  onToggleAlerts,
  onHelp,
}: {
  runs: DetectorRun[] | null;
  runsError: string | null;
  health: FeedHealth;
  alertsOn: boolean;
  alertsBlocked: boolean;
  onToggleAlerts: () => void;
  onHelp: () => void;
}) {
  return (
    <header className="nfz-head">
      <div className="nfz-head-main">
        <div className="nfz-notam">NOTAM // KLYH // SKYWATCH-NFZ</div>
        <h1 className="nfz-title">No-Fly Zone Monitor</h1>
        <p className="nfz-sub">Aircraft that entered restricted, prohibited, or MOA airspace.</p>
        <DetectorStatus runs={runs} error={runsError} />
        {health.message && (
          <div className={`nfz-banner is-${health.level}`} role="alert">
            <b>{health.level === "down" ? "Feed down" : "Feed warning"}</b> {health.message}
          </div>
        )}
      </div>
      <div className="nfz-head-side">
        <ZuluClock />
        <div className="nfz-head-actions">
          <button
            className={`nfz-chip${alertsOn ? " is-on" : ""}`}
            onClick={onToggleAlerts}
            aria-pressed={alertsOn}
            title={
              alertsBlocked
                ? "Sound is on; browser notifications are blocked in this browser's site settings"
                : "Sound + a notification for new HIGH or CRITICAL incursions"
            }
          >
            <span aria-hidden="true">{alertsOn ? "◉" : "○"}</span> Alerts {alertsOn ? "on" : "off"}
          </button>
          <button className="nfz-chip" onClick={onHelp} title="Keyboard shortcuts (?)">
            <kbd>?</kbd> Shortcuts
          </button>
        </div>
      </div>
    </header>
  );
}
