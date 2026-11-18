// The aircraft's altitude over time, drawn against the zone's floor and
// ceiling, with the detector's incursion window shaded. It shows *why* the
// detector fired using only data that already exists; it does not re-judge.
// Click or drag to move the replay.
import { useEffect, useMemo, useRef, useState } from "react";
import { sampleTrack, type TrackPoint } from "../track";
import { limitLabel } from "../altitude";
import { zoneClass, type ZoneInfo } from "../zones";
import { zuluShort } from "../format";
import { ensureHatchDefs } from "../map/svgDefs";

const H = 170;
const M = { l: 46, r: 10, t: 14, b: 22 };

function niceStep(max: number): number {
  for (const s of [500, 1000, 2000, 5000, 10000, 20000]) if (max / s <= 5) return s;
  return 50000;
}
const kft = (ft: number) => (ft === 0 ? "0" : ft % 1000 === 0 ? `${ft / 1000}k` : `${(ft / 1000).toFixed(1)}k`);

export function AltitudeProfile({
  points,
  t,
  onSeek,
  entry,
  exit,
  zone,
}: {
  points: TrackPoint[];
  t: number;
  onSeek: (t: number) => void;
  entry: number | null;
  exit: number | null;
  zone?: ZoneInfo;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(420);
  useEffect(() => {
    ensureHatchDefs();
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(240, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const withAlt = points.filter((p) => p.alt != null);
  const t0 = points[0]?.t ?? 0;
  const t1 = points[points.length - 1]?.t ?? 1;
  const floor = zone ? (zone.floorDatum.toUpperCase() === "SFC" ? 0 : zone.floorFt) : null;
  const ceiling = zone?.ceilingFt ?? null;
  const maxAlt = Math.max(1000, ...withAlt.map((p) => p.alt as number), ceiling != null && ceiling < 60000 ? ceiling : 0);
  const step = niceStep(maxAlt * 1.1);
  const top = Math.ceil((maxAlt * 1.08) / step) * step;
  const x = (time: number) => M.l + ((time - t0) / (t1 - t0 || 1)) * (w - M.l - M.r);
  const y = (ft: number) => M.t + (1 - ft / top) * (H - M.t - M.b);

  const path = useMemo(() => {
    let d = "";
    let pen = false;
    for (const p of points) {
      if (p.alt == null) {
        pen = false;
        continue;
      }
      d += `${pen ? "L" : "M"}${x(p.t).toFixed(1)} ${y(p.alt).toFixed(1)}`;
      pen = true;
    }
    return d;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points, w, top]);

  const cur = sampleTrack(points, t);
  const seekAt = (clientX: number) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    const f = Math.min(1, Math.max(0, (clientX - r.left - M.l) / (w - M.l - M.r)));
    onSeek(t0 + f * (t1 - t0));
  };

  if (withAlt.length < 2) {
    return <div className="nfz-profile nfz-profile--empty">No altitude data in this track.</div>;
  }
  const cls = zone ? zoneClass(zone.type) : "restricted";
  const ticks = Array.from({ length: Math.floor(top / step) + 1 }, (_, i) => i * step);
  const inX0 = entry != null ? x(Math.max(t0, entry)) : null;
  const inX1 = entry != null ? x(Math.min(t1, exit ?? t1)) : null;

  return (
    <div
      ref={box}
      className="nfz-profile"
      onPointerDown={(e) => {
        (e.target as Element).setPointerCapture?.(e.pointerId);
        seekAt(e.clientX);
      }}
      onPointerMove={(e) => e.buttons === 1 && seekAt(e.clientX)}
      role="slider"
      aria-label="Replay position on the altitude profile"
      aria-valuemin={t0}
      aria-valuemax={t1}
      aria-valuenow={Math.round(t)}
    >
      <svg width={w} height={H} viewBox={`0 0 ${w} ${H}`}>
        {/* Zone floor–ceiling band */}
        {zone && floor != null && ceiling != null && (
          <g className={`nfz-pf-band nfz-pf-band--${cls}`}>
            <rect
              x={M.l}
              y={y(Math.min(ceiling, top))}
              width={w - M.l - M.r}
              height={Math.max(0, y(floor) - y(Math.min(ceiling, top)))}
              fill={`url(#nfz-hatch-${cls})`}
            />
            <line x1={M.l} x2={w - M.r} y1={y(Math.min(ceiling, top))} y2={y(Math.min(ceiling, top))} />
            <line
              x1={M.l}
              x2={w - M.r}
              y1={y(floor)}
              y2={y(floor)}
              strokeDasharray={zone.floorDatum.toUpperCase() === "AGL" ? "4 4" : undefined}
            />
            <text x={w - M.r - 4} y={y(Math.min(ceiling, top)) + 12} textAnchor="end">
              {zone.id} {limitLabel(zone.floorFt, zone.floorDatum)}–{limitLabel(zone.ceilingFt, zone.ceilingDatum)}
              {zone.floorDatum.toUpperCase() === "AGL" ? " (floor is above ground level)" : ""}
            </text>
          </g>
        )}
        {/* Incursion window from the detector */}
        {inX0 != null && inX1 != null && (
          <g className="nfz-pf-window">
            <rect x={inX0} y={M.t} width={Math.max(2, inX1 - inX0)} height={H - M.t - M.b} />
            <text x={inX0 + 3} y={M.t + 10}>
              IN
            </text>
            {exit != null && (
              <text x={inX1 + 3} y={M.t + 10}>
                OUT
              </text>
            )}
          </g>
        )}
        {/* Axes */}
        <g className="nfz-pf-axis">
          {ticks.map((ft) => (
            <g key={ft}>
              <line x1={M.l} x2={w - M.r} y1={y(ft)} y2={y(ft)} />
              <text x={M.l - 6} y={y(ft) + 3} textAnchor="end">
                {kft(ft)}
              </text>
            </g>
          ))}
          {[0, 1 / 3, 2 / 3, 1].map((f) => (
            <text key={f} x={M.l + f * (w - M.l - M.r)} y={H - 6} textAnchor={f === 0 ? "start" : f === 1 ? "end" : "middle"}>
              {zuluShort(t0 + f * (t1 - t0))}
            </text>
          ))}
          <text x={4} y={M.t - 4} className="nfz-pf-unit">
            FT
          </text>
        </g>
        {/* Altitude line */}
        <path d={path} className="nfz-pf-line" />
        {/* Replay cursor */}
        {cur && (
          <g className="nfz-pf-cursor">
            <line x1={x(cur.t)} x2={x(cur.t)} y1={M.t} y2={H - M.b} />
            {cur.alt != null && <circle cx={x(cur.t)} cy={y(cur.alt)} r={4} />}
          </g>
        )}
      </svg>
    </div>
  );
}
