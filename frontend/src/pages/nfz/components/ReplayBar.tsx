// Sky replay controls: a slim bar along the bottom of the map that only exists
// while replaying. The track shows the last hour; the lighter band is the part
// this browser has history for, and the small marks are detections (click one
// to jump just before it).
import type { Detection } from "../../../api/types";
import { severityColor } from "../severity";
import { zuluClock, zuluShort } from "../format";
import { HISTORY_MINUTES } from "../trails";
import { SKY_SPEEDS, type SkySpeed } from "../hooks/useSkyReplay";

export function ReplayBar({
  t,
  now,
  playing,
  speed,
  historyFrom,
  detections,
  loading,
  inView,
  onToggle,
  onSeek,
  onSpeed,
  onLoad,
  onClose,
}: {
  t: number;
  now: number;
  playing: boolean;
  speed: SkySpeed;
  historyFrom: number | null;
  detections: Detection[];
  loading: { done: number; total: number } | null;
  inView: number;
  onToggle: () => void;
  onSeek: (t: number) => void;
  onSpeed: (s: SkySpeed) => void;
  onLoad: () => void;
  onClose: () => void;
}) {
  const start = now - HISTORY_MINUTES * 60_000;
  const pct = (x: number) => `${Math.min(100, Math.max(0, ((x - start) / (now - start)) * 100))}%`;
  const marks = detections
    .map((d) => ({ d, at: Date.parse(String(d.temporal_bounds_start ?? d.last_detected_at)) }))
    .filter((m) => Number.isFinite(m.at) && m.at >= start && m.at <= now);
  const minsAgo = Math.max(0, Math.round((now - t) / 60_000));

  return (
    <div className="nfz-replay-bar" role="group" aria-label="Sky replay">
      <span className="nfz-rb-tag">Replay</span>
      <button className="nfz-play nfz-rb-play" onClick={onToggle} aria-label={playing ? "Pause sky replay" : "Play sky replay"}>
        {playing ? "❚❚" : "▶"}
      </button>
      <div className="nfz-rb-track">
        {historyFrom != null && (
          <div className="nfz-rb-have" style={{ left: pct(historyFrom) }} title={`History recorded from ${zuluShort(historyFrom)}`} />
        )}
        {[1, 2, 3, 4, 5].map((k) => (
          <span key={k} className="nfz-rb-tick" style={{ left: `${(k / 6) * 100}%` }}>
            −{60 - k * 10}m
          </span>
        ))}
        {marks.map(({ d, at }) => (
          <button
            key={d.detection_id}
            className="nfz-rb-mark"
            style={{ left: pct(at), ["--mc" as string]: severityColor(d.severity) }}
            title={`${String(d.severity).toUpperCase()} · ${d.entity_id}${d.zone_id ? ` · ${String(d.zone_id)}` : ""} · ${zuluShort(at)}`}
            aria-label={`Jump to ${String(d.severity)} detection at ${zuluShort(at)}`}
            onClick={() => onSeek(at - 30_000)}
          />
        ))}
        <input
          type="range"
          min={start}
          max={now}
          step={1000}
          value={Math.round(t)}
          onChange={(e) => onSeek(Number(e.target.value))}
          aria-label="Replay time"
        />
      </div>
      <span className="nfz-rb-time">
        <b>{zuluClock(t)}</b>
        <em>{minsAgo ? `−${minsAgo} min` : "now"}</em>
      </span>
      <div className="nfz-speeds" role="group" aria-label="Replay speed">
        {SKY_SPEEDS.map((s) => (
          <button key={s} className={s === speed ? "is-on" : undefined} onClick={() => onSpeed(s)}>
            {s}×
          </button>
        ))}
      </div>
      <button
        className="nfz-mapbtn nfz-rb-load"
        onClick={onLoad}
        disabled={!!loading || inView === 0}
        title="Fetch the last hour of track for the aircraft in view, so replay can show them from the start"
      >
        {loading ? (
          `Loading ${loading.done}/${loading.total}`
        ) : (
          <>
            <span className="nfz-rb-wide">Load history </span>
            <span className="nfz-rb-narrow">History </span>({inView})
          </>
        )}
      </button>
      <button className="nfz-mapbtn" onClick={onClose} title="Back to live (R)">
        Live ✕
      </button>
    </div>
  );
}
