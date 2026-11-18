// No-fly-zone map overlay (NFZ team). MapPage.tsx renders this inside the
// shared <MapView>, and so does our own dashboard. It is a thin wrapper: each
// layer lives in its own file under ../nfz/map/.
//
// It only draws what the detector and the feed already say; it never decides
// on its own whether something is an incursion.
import { useMemo } from "react";
import type { Detection } from "../../api/types";
import { buildFlagged } from "../nfz/flagged";
import { ZoneLayer } from "../nfz/map/ZoneLayer";
import { IncursionLayer } from "../nfz/map/IncursionLayer";
import { PingLayer } from "../nfz/map/PingLayer";
import { TrafficLayer } from "../nfz/map/TrafficLayer";
import { ChartLayer } from "../nfz/map/ChartLayer";
import { MapLegend } from "../nfz/map/MapLegend";
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "../nfz/map/map.css";

export type TrafficStyle = "lines" | "planes" | "none";

export function NoFlyZoneOverlay({
  detections,
  selectedId,
  traffic = "lines",
  pingIds,
  focusZoneId,
  chart = false,
  showPlanes = true,
  showTrails = true,
  showTags = true,
  legendClosed,
  onSelect,
  onZoneClick,
  dashboardLinks = false,
}: {
  detections: Detection[];
  selectedId?: string | null;
  // How to draw live traffic: "lines" next to the shared map's aircraft dots,
  // "planes" for our own plane icons, "none" for small embedded maps.
  traffic?: TrafficStyle;
  // Detections that just arrived: they get a ripple.
  pingIds?: ReadonlySet<string>;
  // The zone picked on the zone board (white outline).
  focusZoneId?: string | null;
  // Grid, range rings, compass rose and airport symbol.
  chart?: boolean;
  showPlanes?: boolean;
  showTrails?: boolean;
  showTags?: boolean;
  legendClosed?: boolean;
  onSelect?: (d: Detection) => void;
  onZoneClick?: (zoneId: string) => void;
  /** Incursion popups link to the replay on the NFZ dashboard (for /map). */
  dashboardLinks?: boolean;
}) {
  // Aircraft with a recent (or the selected) incursion get lock-on brackets.
  const hot = useMemo(() => buildFlagged(detections, selectedId), [detections, selectedId]);

  return (
    <>
      {chart && <ChartLayer />}
      <ZoneLayer detections={detections} focusZoneId={focusZoneId} onZoneClick={onZoneClick} />
      {traffic !== "none" && (
        <TrafficLayer
          mode={traffic}
          hot={hot}
          showPlanes={showPlanes}
          showTrails={showTrails}
          showTags={showTags}
        />
      )}
      <IncursionLayer
        detections={detections}
        selectedId={selectedId}
        ringLive={traffic === "lines"}
        onSelect={onSelect}
        dashboardLinks={dashboardLinks}
      />
      <PingLayer detections={detections} pingIds={pingIds} />
      {traffic !== "none" && <MapLegend traffic={traffic} chart={chart} startClosed={legendClosed} />}
    </>
  );
}
