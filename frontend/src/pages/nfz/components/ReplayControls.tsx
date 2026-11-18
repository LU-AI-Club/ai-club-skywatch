import { altitudeTag } from "../altitude";
import { zuluClock } from "../format";
import { REPLAY_SPEEDS, type ReplaySpeed } from "../hooks/useReplay";
import type { TrackSample } from "../track";

export function ReplayControls({
  start,
  end,
  t,
  playing,
  speed,
  sample,
  inside,
  onToggle,
  onSeek,
  onSpeed,
}: {
  start: number;
  end: number;
  t: number;
  playing: boolean;
  speed: ReplaySpeed;
  sample: TrackSample | null;
  inside: boolean;
  onToggle: () => void;
  onSeek: (t: number) => void;
  onSpeed: (s: ReplaySpeed) => void;
}) {
  return (
    <div className="nfz-replay">
      <div className="nfz-replay-row">
        <button className="nfz-play" onClick={onToggle} aria-label={playing ? "Pause replay" : "Play replay"}>
          {playing ? "❚❚" : "▶"}
        </button>
        <input
          className="nfz-scrub"
          type="range"
          min={start}
          max={end}
          step={1000}
          value={Math.round(t)}
          onChange={(e) => onSeek(Number(e.target.value))}
          aria-label="Replay position"
        />
        <div className="nfz-speeds" role="group" aria-label="Replay speed">
          {REPLAY_SPEEDS.map((s) => (
            <button key={s} className={s === speed ? "is-on" : undefined} onClick={() => onSpeed(s)}>
              {s}×
            </button>
          ))}
        </div>
      </div>
      <div className="nfz-replay-readouts">
        <span>
          <b>{zuluClock(t)}</b>
        </span>
        <span>
          ALT <b>{sample?.alt != null ? `${altitudeTag(sample.alt)}` : "---"}</b>
        </span>
        <span>
          SPD <b>{sample?.sog != null ? `${Math.round(sample.sog)} KT` : "---"}</b>
        </span>
        <span>
          TRK <b>{sample?.course != null ? `${String(Math.round(sample.course)).padStart(3, "0")}°` : "---"}</b>
        </span>
        <span className={`nfz-inzone${inside ? " is-in" : ""}`}>{inside ? "IN ZONE" : "OUTSIDE"}</span>
      </div>
    </div>
  );
}
