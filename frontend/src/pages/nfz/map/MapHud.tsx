// Heads-up display over a live map: a status strip (Zulu clock, traffic,
// low traffic, flagged detections, emergencies, feed age), the cursor
// position in chart coordinates, a nautical-mile scale bar, and corner
// brackets.
import { useEffect, useState } from "react";
import type { LeafletMouseEvent } from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { useObservations } from "../../../api/observations";
import { altitudeFt } from "../altitude";
import { dms, zuluClock } from "../format";
import { project } from "../geo";
import { emergencyOf } from "../squawk";
import { useNow } from "../hooks/useNow";
import { fmtAge, type FeedHealth } from "../hooks/useFeedHealth";

const NICE_NM = [0.5, 1, 2, 5, 10, 20, 50, 100, 200];

export function MapHud({
  flagged,
  flaggedLabel = "incursions",
  health,
}: {
  flagged: number;
  flaggedLabel?: string;
  health: FeedHealth;
}) {
  const map = useLeafletMap();
  const { aircraft } = useObservations();
  const now = useNow(1000);
  const [cursor, setCursor] = useState<{ lat: number; lng: number } | null>(null);
  const [scale, setScale] = useState<{ nm: number; px: number } | null>(null);
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (!map) return;
    let frame = 0;
    const onMove = (e: LeafletMouseEvent) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => setCursor(e.latlng));
    };
    const onOut = () => setCursor(null);
    const updateScale = () => {
      const c = map.getCenter();
      const one = project({ lat: c.lat, lon: c.lng }, 90, 1);
      const pxPerNm = Math.abs(map.latLngToContainerPoint([one.lat, one.lon]).x - map.latLngToContainerPoint(c).x);
      if (!pxPerNm) return;
      const nm = [...NICE_NM].reverse().find((v) => v * pxPerNm <= 110) ?? NICE_NM[0];
      setScale({ nm, px: nm * pxPerNm });
      setCenter(c);
    };
    updateScale();
    map.on("mousemove", onMove);
    map.on("mouseout", onOut);
    map.on("zoomend moveend resize", updateScale);
    return () => {
      cancelAnimationFrame(frame);
      map.off("mousemove", onMove);
      map.off("mouseout", onOut);
      map.off("zoomend moveend resize", updateScale);
    };
  }, [map]);

  let low = 0;
  let emergencies = 0;
  for (const a of aircraft) {
    const ft = altitudeFt(a.properties.altitude);
    if (ft != null && ft > 0 && ft < 5000) low++;
    if (emergencyOf(a.properties.squawk)) emergencies++;
  }
  const feedText =
    health.level === "down"
      ? "FEED DOWN"
      : health.newestAgeS == null
        ? "FEED —"
        : `FEED ${fmtAge(health.newestAgeS).toUpperCase()}`;

  return (
    <>
      <div className="nfz-reticle" aria-hidden="true">
        <i />
      </div>
      <div className="nfz-hud-corners" aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </div>
      <div className="nfz-hud-strip" role="status">
        <span className="is-clock">{zuluClock(now)}</span>
        <span>
          <b>{aircraft.length}</b> traffic
        </span>
        <span className="is-low">
          <b>{low}</b> below 5k ft
        </span>
        <span className={flagged ? "is-alert" : undefined}>
          <b>{flagged}</b> {flaggedLabel}
        </span>
        {emergencies > 0 && (
          <span className="is-emerg">
            <b>{emergencies}</b> emergency squawk{emergencies > 1 ? "s" : ""}
          </span>
        )}
        <span className={`is-feed is-${health.level}`}>{feedText}</span>
      </div>
      <div className="nfz-hud-readout" aria-hidden="true">
        {scale && (
          <div className="nfz-scale">
            <i style={{ width: `${Math.round(scale.px)}px` }} />
            <span>{scale.nm} NM</span>
          </div>
        )}
        <div className="nfz-cursor">
          {cursor ? (
            <>
              <em>CURSOR</em> {dms(cursor.lat, "lat")} {dms(cursor.lng, "lon")}
            </>
          ) : center ? (
            <>
              <em>CENTER</em> {dms(center.lat, "lat")} {dms(center.lng, "lon")}
            </>
          ) : null}
        </div>
      </div>
    </>
  );
}
