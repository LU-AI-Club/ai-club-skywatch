// The live airspace map used by both the NFZ dashboard and the shared /map
// page: chart-style basemap and decorations, live traffic with trails and
// data tags, a HUD, layer switches (with optional context layers), aircraft
// search, measuring, the selected aircraft's flight strip (with follow), sky
// replay, a legend, and fullscreen. Detector overlays are passed in as
// children. Calm by default: optional layers start off, replay controls only
// appear while replaying.
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
import { fetchJSON } from "../../../api/client";
import { ChartLayer } from "../map/ChartLayer";
import { TrafficLayer } from "../map/TrafficLayer";
import { MapLegend } from "../map/MapLegend";
import { MapHud } from "../map/MapHud";
import { AircraftSearch } from "../map/AircraftSearch";
import { LayerSwitch, loadLayers, saveLayers, type MapLayers } from "../map/LayerSwitch";
import { FlyTo, InvalidateOnChange, ScrollGuard } from "../map/MapBehavior";
import { SweepLayer, prefersReducedMotion } from "../map/SweepLayer";
import { MeasureTool } from "../map/MeasureTool";
import { WeatherLayer } from "../map/WeatherLayer";
import { AirportsLayer, NavaidsLayer } from "../map/ContextPoints";
import { DayNightLayer } from "../map/DayNightLayer";
import { HeatmapLayer } from "../map/HeatmapLayer";
import { ReplayContext, asOf } from "../map/replayContext";
import { buildFlagged } from "../flagged";
import { HISTORY_MINUTES, aircraftMeta, trails } from "../trails";
import { aircraftAt, historyStart, mergeTrack } from "../replay";
import { parseTrack, type TrackResponse } from "../track";
import { useSkyReplay } from "../hooks/useSkyReplay";
import type { FeedHealth } from "../hooks/useFeedHealth";
import type { ZoneInfo } from "../zones";
import { FlightStrip } from "./FlightStrip";
import { ReplayBar } from "./ReplayBar";
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
  /** Open or close sky replay. */
  toggleReplay: () => void;
};

type Props = {
  /** Detections that can flag aircraft (lock-on brackets, flight strip list, heatmap, replay marks). */
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

const LOAD_CAP = 80; // most aircraft "Load history" fetches at once
const LOAD_PARALLEL = 4;

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
  const { aircraft: live } = useObservations();
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

  // ---------------------------------------------------------- sky replay
  const sky = useSkyReplay();
  const replayAt = sky.on ? sky.t : null;
  const [historyVersion, setHistoryVersion] = useState(0); // bumps after "Load history"
  const [loading, setLoading] = useState<{ done: number; total: number } | null>(null);
  const loadAbort = useRef<AbortController | null>(null);
  const shown = useMemo(
    () => (replayAt == null ? live : aircraftAt(trails, aircraftMeta, replayAt)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [replayAt, live, historyVersion],
  );
  const flaggedNow = useMemo(() => asOf(flagged, replayAt), [flagged, replayAt]);
  const hot = useMemo(
    () => buildFlagged(flaggedNow, selectedDetectionId, replayAt ?? Date.now()),
    [flaggedNow, selectedDetectionId, replayAt],
  );
  const inView = useMemo(() => {
    const map = mapRef.current;
    if (!map || !sky.on) return 0;
    const b = map.getBounds();
    return Math.min(LOAD_CAP, live.filter((a) => b.contains([a.geometry.coordinates[1], a.geometry.coordinates[0]])).length);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, sky.on, sky.now]);

  const loadHistory = useCallback(async () => {
    const map = mapRef.current;
    if (!map) return;
    const b = map.getBounds().pad(0.1);
    const ids = live
      .filter((a) => b.contains([a.geometry.coordinates[1], a.geometry.coordinates[0]]))
      .slice(0, LOAD_CAP)
      .map((a) => a.id);
    if (!ids.length) return;
    loadAbort.current?.abort();
    const controller = new AbortController();
    loadAbort.current = controller;
    const queue = [...ids];
    let done = 0;
    setLoading({ done, total: ids.length });
    const keepAfter = Date.now() - HISTORY_MINUTES * 60_000;
    const worker = async () => {
      while (queue.length && !controller.signal.aborted) {
        const id = queue.shift()!;
        try {
          const res = await fetchJSON<TrackResponse>(
            "/observations/tracks",
            { entity_id: id, lookback_hours: HISTORY_MINUTES / 60, limit: 10000 },
            controller.signal,
          );
          mergeTrack(trails, id, parseTrack(res), 10_000, keepAfter);
        } catch {
          if (controller.signal.aborted) return;
        }
        done++;
        setLoading({ done, total: ids.length });
      }
    };
    await Promise.all(Array.from({ length: LOAD_PARALLEL }, worker));
    if (!controller.signal.aborted) {
      setHistoryVersion((v) => v + 1);
      window.setTimeout(() => setLoading(null), 600);
    }
  }, [live]);

  const closeReplay = useCallback(() => {
    loadAbort.current?.abort();
    setLoading(null);
    sky.close();
  }, [sky]);
  const toggleReplay = useCallback(() => (sky.on ? closeReplay() : sky.open()), [sky, closeReplay]);
  useEffect(() => () => loadAbort.current?.abort(), []);

  // ---------------------------------------------------------- fullscreen
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

  // ---------------------------------------------------------- selection
  const flyToAircraft = useCallback(
    (id: string) => {
      const a = shown.find((x) => x.id === id);
      const map = mapRef.current;
      if (!a || !map) return;
      const [lon, lat] = a.geometry.coordinates;
      map.flyTo([lat, lon], Math.max(map.getZoom(), 10), { duration: 0.8 });
    },
    [shown],
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
    if (!live.some((a) => a.id === id)) return;
    pending.current = null;
    setSelected(id);
    setFollow(true);
    flyToAircraft(id);
  }, [live, flyToAircraft]);

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
      toggleReplay,
    }),
    [toggleFullscreen, selected, toggleReplay],
  );

  const selectAircraft = useCallback((id: string | null) => {
    setSelected(id);
    if (!id) setFollow(false);
  }, []);

  return (
    <div
      ref={box}
      className={`nfz-map nfz-chartmap${expanded ? " is-expanded" : ""}${sky.on ? " is-replaying" : ""}${className ? ` ${className}` : ""}`}
    >
      <MapView showAircraft={false} style={{ height: "100%" }} onReady={(m) => (mapRef.current = m)}>
        <ReplayContext.Provider value={replayAt}>
          {layers.weather && <WeatherLayer />}
          {layers.daynight && <DayNightLayer />}
          {layers.chart && <ChartLayer />}
          {layers.heatmap && <HeatmapLayer detections={flaggedNow} />}
          {layers.airports && <AirportsLayer skip={layers.chart ? ["KLYH"] : []} />}
          {layers.navaids && <NavaidsLayer />}
          {children}
          <TrafficLayer
            mode="planes"
            aircraft={shown}
            replayAt={replayAt}
            hot={hot}
            showPlanes={layers.traffic}
            showTrails={layers.trails}
            tagMode={layers.tags}
            selected={selected}
            onSelect={selectAircraft}
            follow={follow}
            onFollowChange={setFollow}
            sweep={sweepOn}
          />
          {sweepOn && <SweepLayer />}
          <MeasureTool active={measuring} onDone={stopMeasuring} />
          <MapLegend
            traffic="planes"
            zones={zonesInLegend}
            chart={layers.chart}
            extras={{
              weather: layers.weather,
              airports: layers.airports,
              navaids: layers.navaids,
              daynight: layers.daynight,
              heatmap: layers.heatmap,
            }}
          />
          <FlyTo zone={focusZone} point={flyPoint} />
          {embedded && <ScrollGuard />}
          <InvalidateOnChange dep={`${isFull}-${expanded}`} />
          <MapHud
            flagged={flaggedNow.length}
            flaggedLabel={flaggedLabel}
            health={health}
            aircraft={shown}
            replayAt={replayAt}
          />
          <LayerSwitch layers={layers} onChange={setLayers} isFull={isFull || expanded} onFullscreen={toggleFullscreen}>
            <AircraftSearch ref={searchRef} onPick={pick} aircraft={shown} />
            <button
              className={`nfz-mapbtn${measuring ? " is-on" : ""}`}
              aria-pressed={measuring}
              onClick={() => setMeasuring((m) => !m)}
              title="Measure distance and bearing: click two points (Esc to stop)"
            >
              {measuring ? "Measuring…" : "Measure"}
            </button>
            <button
              className={`nfz-mapbtn${sky.on ? " is-replay" : ""}`}
              aria-pressed={sky.on}
              onClick={toggleReplay}
              title="Sky replay: play back all traffic from the last hour (R)"
            >
              Replay
            </button>
          </LayerSwitch>
          {selected && (
            <FlightStrip
              id={selected}
              detections={flagged}
              follow={follow}
              onFollow={setFollow}
              onClose={() => selectAircraft(null)}
              aircraft={shown}
              replayAt={replayAt}
            />
          )}
          {sky.on && (
            <ReplayBar
              t={sky.t}
              now={sky.now}
              playing={sky.playing}
              speed={sky.speed}
              historyFrom={historyStart(trails)}
              detections={flagged}
              loading={loading}
              inView={inView}
              onToggle={sky.toggle}
              onSeek={(x) => {
                sky.setPlaying(false);
                sky.seek(x);
              }}
              onSpeed={sky.setSpeed}
              onLoad={() => void loadHistory()}
              onClose={closeReplay}
            />
          )}
        </ReplayContext.Provider>
      </MapView>
    </div>
  );
});
