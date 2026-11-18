// The live airspace map used by both the NFZ dashboard and the shared /map
// page: chart-style basemap and decorations, live traffic with trails and
// data tags, a HUD, layer switches, aircraft search, the selected aircraft's
// flight strip (with follow), a legend, and fullscreen. Detector overlays
// are passed in as children.
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { Map as LeafletMap } from "leaflet";
import type { Detection } from "../../../api/types";
import { MapView } from "../../../map/MapView";
import { useObservations } from "../../../api/observations";
import { ChartLayer } from "../map/ChartLayer";
import { TrafficLayer } from "../map/TrafficLayer";
import { MapLegend } from "../map/MapLegend";
import { MapHud } from "../map/MapHud";
import { AircraftSearch } from "../map/AircraftSearch";
import { LayerSwitch, loadLayers, saveLayers, type MapLayers } from "../map/LayerSwitch";
import { FlyTo, InvalidateOnChange, ScrollGuard } from "../map/MapBehavior";
import { SweepLayer, prefersReducedMotion } from "../map/SweepLayer";
import { MeasureTool } from "../map/MeasureTool";
import { buildFlagged } from "../flagged";
import type { FeedHealth } from "../hooks/useFeedHealth";
import type { ZoneInfo } from "../zones";
import { FlightStrip } from "./FlightStrip";
import "@fontsource/barlow-condensed/500.css";
import "@fontsource/barlow-condensed/700.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "../map/map.css";

export type LiveMapHandle = {
  toggleFullscreen: () => void;
  focusSearch: () => void;
  /** Close the flight strip; returns false if nothing was selected. */
  clearSelection: () => boolean;
};

type Props = {
  /** Detections that can flag aircraft (lock-on brackets, flight strip list). */
  flagged: Detection[];
  /** Label for the flagged count in the HUD. */
  flaggedLabel?: string;
  selectedDetectionId?: string | null;
  health: FeedHealth;
  /** Inside a scrolling page (the dashboard): wheel scrolls the page until the map is clicked. */
  embedded?: boolean;
  /** Show the airspace entries in the legend. */
  zonesInLegend?: boolean;
  focusZone?: ZoneInfo | null;
  flyPoint?: { lat: number; lon: number; key: string } | null;
  /** Select (and follow) this aircraft once it shows up in the feed, e.g. from ?ac=. */
  initialAircraft?: string | null;
  className?: string;
  children?: ReactNode;
};

export const LiveMap = forwardRef<LiveMapHandle, Props>(function LiveMap(
  {
    flagged,
    flaggedLabel = "incursions",
    selectedDetectionId,
    health,
    embedded = false,
    zonesInLegend = true,
    focusZone = null,
    flyPoint = null,
    initialAircraft = null,
    className = "",
    children,
  },
  ref,
) {
  const box = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const { aircraft } = useObservations();
  const [layers, setLayersState] = useState<MapLayers>(loadLayers);
  const [isFull, setIsFull] = useState(false);
  const [expanded, setExpanded] = useState(false); // fallback when the browser refuses fullscreen
  const [selected, setSelected] = useState<string | null>(null);
  const [follow, setFollow] = useState(false);
  const [measuring, setMeasuring] = useState(false);
  const stopMeasuring = useCallback(() => setMeasuring(false), []);
  const sweepOn = layers.sweep && !prefersReducedMotion();
  const setLayers = (l: MapLayers) => {
    setLayersState(l);
    saveLayers(l);
  };

  const hot = useMemo(() => buildFlagged(flagged, selectedDetectionId), [flagged, selectedDetectionId]);

  useEffect(() => {
    const onChange = () => setIsFull(document.fullscreenElement === box.current);
    document.addEventListener("fullscreenchange", onChange);
    return () => document.removeEventListener("fullscreenchange", onChange);
  }, []);

  useEffect(() => {
    if (!expanded) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setExpanded(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [expanded]);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      void document.exitFullscreen();
      return;
    }
    if (expanded) {
      setExpanded(false);
      return;
    }
    const el = box.current;
    if (!el?.requestFullscreen) setExpanded(true);
    else el.requestFullscreen().catch(() => setExpanded(true));
  }, [expanded]);

  const flyToAircraft = useCallback(
    (id: string) => {
      const a = aircraft.find((x) => x.id === id);
      const map = mapRef.current;
      if (!a || !map) return;
      const [lon, lat] = a.geometry.coordinates;
      map.flyTo([lat, lon], Math.max(map.getZoom(), 10), { duration: 0.8 });
    },
    [aircraft],
  );

  const pick = useCallback(
    (id: string) => {
      setSelected(id);
      setFollow(false);
      flyToAircraft(id);
    },
    [flyToAircraft],
  );

  // ?ac= links: select and follow the aircraft once it is in the feed.
  const pending = useRef(initialAircraft?.toLowerCase() ?? null);
  useEffect(() => {
    const id = pending.current;
    if (!id || !mapRef.current) return;
    if (!aircraft.some((a) => a.id === id)) return;
    pending.current = null;
    setSelected(id);
    setFollow(true);
    flyToAircraft(id);
  }, [aircraft, flyToAircraft]);

  useImperativeHandle(
    ref,
    () => ({
      toggleFullscreen,
      focusSearch: () => searchRef.current?.focus(),
      clearSelection: () => {
        if (!selected) return false;
        setSelected(null);
        setFollow(false);
        return true;
      },
    }),
    [toggleFullscreen, selected],
  );

  // Start the legend folded on small screens (unless the user opened it before).
  const narrow =
    typeof window !== "undefined" && !!window.matchMedia?.("(max-width: 640px), (max-height: 760px)").matches;
  const selectAircraft = useCallback((id: string | null) => {
    setSelected(id);
    if (!id) setFollow(false);
  }, []);

  return (
    <div
      ref={box}
      className={`nfz-map nfz-chartmap${expanded ? " is-expanded" : ""}${className ? ` ${className}` : ""}`}
    >
      <MapView showAircraft={false} style={{ height: "100%" }} onReady={(m) => (mapRef.current = m)}>
        {layers.chart && <ChartLayer />}
        {children}
        <TrafficLayer
          mode="planes"
          hot={hot}
          showPlanes={layers.traffic}
          showTrails={layers.trails}
          showTags={layers.tags}
          selected={selected}
          onSelect={selectAircraft}
          follow={follow}
          onFollowChange={setFollow}
          sweep={sweepOn}
        />
        {sweepOn && <SweepLayer />}
        <MeasureTool active={measuring} onDone={stopMeasuring} />
        <MapLegend traffic="planes" zones={zonesInLegend} chart={layers.chart} startClosed={narrow} />
        <FlyTo zone={focusZone} point={flyPoint} />
        {embedded && <ScrollGuard />}
        <InvalidateOnChange dep={`${isFull}-${expanded}`} />
        <MapHud flagged={flagged.length} flaggedLabel={flaggedLabel} health={health} />
        <LayerSwitch layers={layers} onChange={setLayers} isFull={isFull || expanded} onFullscreen={toggleFullscreen}>
          <AircraftSearch ref={searchRef} onPick={pick} />
          <button
            className={`nfz-mapbtn${measuring ? " is-on" : ""}`}
            aria-pressed={measuring}
            onClick={() => setMeasuring((m) => !m)}
            title="Measure distance and bearing: click two points (Esc to stop)"
          >
            {measuring ? "Measuring…" : "Measure"}
          </button>
        </LayerSwitch>
        {selected && (
          <FlightStrip
            id={selected}
            detections={flagged}
            follow={follow}
            onFollow={setFollow}
            onClose={() => selectAircraft(null)}
          />
        )}
      </MapView>
    </div>
  );
});
