// The selected aircraft's "flight strip", like the paper strips controllers
// use: callsign, codes, altitude and climb rate, speed, track, position, and
// any recent detections for it. Follow keeps the map centered on it.
import { useRef } from "react";
import { Link } from "react-router-dom";
import type { AircraftFeature, Detection } from "../../../api/types";
import { useObservations } from "../../../api/observations";
import { SeverityBadge } from "../../../components/SeverityBadge";
import { altitudeFt } from "../altitude";
import { ago, dms, zuluClock } from "../format";
import { trails, verticalRate, trendArrow } from "../trails";
import { emergencyOf } from "../squawk";
import { isRecent } from "../flagged";
import { callsignOf } from "../map/TrafficLayer";
import { KLYH, nmBetween } from "../geo";
import { bearing } from "../track";

const DETECTOR_NAMES: Record<string, string> = {
  no_fly_zone: "No-fly zone",
  spoofing: "Spoofing",
  proximity: "Proximity",
};
function detectorName(id: string): string {
  const key = Object.keys(DETECTOR_NAMES).find((k) => id.includes(k));
  return key ? DETECTOR_NAMES[key] : id;
}

export function FlightStrip({
  id,
  detections,
  follow,
  onFollow,
  onClose,
  aircraft: list,
  replayAt = null,
}: {
  id: string;
  detections: Detection[];
  follow: boolean;
  onFollow: (on: boolean) => void;
  onClose: () => void;
  /** What the map is showing (sky replay passes past positions). */
  aircraft?: AircraftFeature[];
  replayAt?: number | null;
}) {
  const { aircraft: live } = useObservations();
  const aircraft = list ?? live;
  const found = aircraft.find((a) => a.id === id);
  const lastSeen = useRef<AircraftFeature | null>(null);
  if (found) lastSeen.current = found;
  const a = found ?? lastSeen.current;

  if (!a) {
    return (
      <aside className="nfz-strip" aria-label="Selected aircraft">
        <div className="nfz-strip-head">
          <div>
            <div className="nfz-strip-call">{id.toUpperCase()}</div>
            <div className="nfz-strip-sub">Not in the live feed right now</div>
          </div>
          <button className="nfz-strip-x" onClick={onClose} aria-label="Close flight strip">
            ✕
          </button>
        </div>
      </aside>
    );
  }

  const p = a.properties;
  const ft = altitudeFt(p.altitude);
  const history = trails.get(a.id) ?? [];
  const rate = verticalRate(replayAt == null ? history : history.filter((f) => f.t <= replayAt));
  const emerg = emergencyOf(p.squawk);
  const mine = detections
    .filter((d) => d.entity_id === `icao24:${p.icao24}` && isRecent(d, replayAt ?? Date.now()))
    .filter((d) => replayAt == null || Date.parse(String(d.temporal_bounds_start)) <= replayAt)
    .sort((x, y) => Date.parse(String(y.last_detected_at)) - Date.parse(String(x.last_detected_at)))
    .slice(0, 4);
  const [lon, lat] = a.geometry.coordinates;
  const fromKlyh = { brg: Math.round(bearing(KLYH, { lat, lon })) % 360, nm: nmBetween(KLYH, { lat, lon }) };

  return (
    <aside className={`nfz-strip${emerg ? " is-emerg" : ""}`} aria-label={`Flight strip for ${callsignOf(p)}`}>
      <div className="nfz-strip-head">
        <div>
          <div className="nfz-strip-call">{callsignOf(p)}</div>
          <div className="nfz-strip-sub">
            ICAO {p.icao24}
            {p.category ? ` · CAT ${p.category}` : ""}
            {p.squawk ? ` · SQK ${p.squawk}` : ""}
          </div>
        </div>
        <button className="nfz-strip-x" onClick={onClose} aria-label="Close flight strip" title="Close (Esc)">
          ✕
        </button>
      </div>
      {emerg && (
        <div className="nfz-strip-emerg">
          SQUAWK {p.squawk} · {emerg.toUpperCase()}
        </div>
      )}
      {replayAt != null && <div className="nfz-strip-replay">Replay · as of {zuluClock(replayAt)}</div>}
      {!found && replayAt == null && <div className="nfz-strip-lost">Lost from the live feed · last known values</div>}
      <dl className="nfz-strip-grid">
        <div>
          <dt>ALT</dt>
          <dd>{ft == null ? "—" : ft <= 0 ? "GND" : `${Math.round(ft).toLocaleString("en-US")} ft`}</dd>
        </div>
        <div>
          <dt>V/S</dt>
          <dd>
            {rate == null
              ? "—"
              : `${rate > 0 ? "+" : rate < 0 ? "−" : ""}${Math.abs(Math.round(rate / 50) * 50).toLocaleString("en-US")} fpm`}{" "}
            {trendArrow(rate)}
          </dd>
        </div>
        <div>
          <dt>SPD</dt>
          <dd>{p.sog == null ? "—" : `${Math.round(p.sog)} kt`}</dd>
        </div>
        <div>
          <dt>TRK</dt>
          <dd>{(p.cog ?? p.heading) == null ? "—" : `${String(Math.round((p.cog ?? p.heading)!)).padStart(3, "0")}°`}</dd>
        </div>
      </dl>
      <div className="nfz-strip-pos">
        {dms(lat, "lat")} {dms(lon, "lon")}
        <span>
          KLYH {String(fromKlyh.brg).padStart(3, "0")}° / {fromKlyh.nm < 10 ? fromKlyh.nm.toFixed(1) : Math.round(fromKlyh.nm)} NM
          {replayAt == null && <> · seen {ago(p.observed_at)}</>}
        </span>
      </div>
      {mine.length > 0 && (
        <ul className="nfz-strip-dets">
          {mine.map((d) => (
            <li key={d.detection_id}>
              <SeverityBadge severity={d.severity} />
              <span>
                {detectorName(d.detector_id)}
                {d.zone_id ? ` · ${String(d.zone_id)}` : ""}
              </span>
              {d.detector_id.includes("no_fly_zone") && (
                <Link to={`/no-fly-zone?d=${encodeURIComponent(d.detection_id)}`}>replay →</Link>
              )}
            </li>
          ))}
        </ul>
      )}
      <div className="nfz-strip-actions">
        <button className={`nfz-chip${follow ? " is-on" : ""}`} aria-pressed={follow} onClick={() => onFollow(!follow)}>
          <span aria-hidden="true">{follow ? "◉" : "○"}</span> Follow
        </button>
        <span className="nfz-meta">track: last 60 min</span>
      </div>
    </aside>
  );
}
