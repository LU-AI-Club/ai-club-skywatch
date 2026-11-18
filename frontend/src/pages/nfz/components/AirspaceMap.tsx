// The NFZ dashboard's big map: the shared LiveMap plus our zones and
// incursions.
import { forwardRef } from "react";
import type { Detection } from "../../../api/types";
import { NoFlyZoneOverlay } from "../../overlays/NoFlyZoneOverlay";
import type { FeedHealth } from "../hooks/useFeedHealth";
import type { ZoneInfo } from "../zones";
import { LiveMap, type LiveMapHandle } from "./LiveMap";

export type AirspaceMapHandle = LiveMapHandle;

export const AirspaceMap = forwardRef<
  AirspaceMapHandle,
  {
    rows: Detection[];
    selectedId: string | null;
    fresh: ReadonlySet<string>;
    focusZone: ZoneInfo | null;
    flyPoint: { lat: number; lon: number; key: string } | null;
    health: FeedHealth;
    onSelect: (d: Detection) => void;
    onZoneClick: (id: string) => void;
  }
>(function AirspaceMap({ rows, selectedId, fresh, focusZone, flyPoint, health, onSelect, onZoneClick }, ref) {
  return (
    <LiveMap
      ref={ref}
      embedded
      flagged={rows}
      selectedDetectionId={selectedId}
      health={health}
      focusZone={focusZone}
      flyPoint={flyPoint}
    >
      <NoFlyZoneOverlay
        detections={rows}
        selectedId={selectedId}
        traffic="none"
        pingIds={fresh}
        focusZoneId={focusZone?.id ?? null}
        onSelect={onSelect}
        onZoneClick={onZoneClick}
      />
    </LiveMap>
  );
});
