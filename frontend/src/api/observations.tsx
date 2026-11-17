// The shared live-aircraft feed. ONE timer polls /observations.geojson for the
// whole app; every view reads the same state through useObservations(). This is
// the single refresh timer the plan calls for — there is never more than one
// aircraft fetch loop, no matter how many views are mounted.
import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { config } from "../config";
import { fetchJSON } from "./client";
import { createSimulation, simulationSettings } from "./simulator";
import type { AircraftFeature, FeatureCollection } from "./types";

interface ObservationsState {
  aircraft: AircraftFeature[];
  loading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  // True when the feed is fake aircraft from the simulator, not the API.
  simulated: boolean;
  refresh: () => void;
}

// How often simulated aircraft move. Faster than the real poll so motion looks smooth.
const SIM_TICK_MS = 1000;

const ObservationsContext = createContext<ObservationsState | null>(null);

export function ObservationsProvider({
  children,
  lookbackHours = config.observationsLookbackHours,
  limit = 2000,
}: {
  children: ReactNode;
  lookbackHours?: number;
  limit?: number;
}) {
  const [aircraft, setAircraft] = useState<AircraftFeature[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const refreshRef = useRef<() => void>(() => {});
  // Read once per page load; changing it means reloading with a new ?simulate.
  const [simulation] = useState(simulationSettings);

  useEffect(() => {
    // Simulation mode (?simulate in the URL): fake aircraft instead of the API.
    if (simulation) {
      const sim = createSimulation(simulation);
      let last = performance.now();
      const tick = () => {
        const now = performance.now();
        setAircraft(sim.tick((now - last) / 1000));
        last = now;
        setError(null);
        setLoading(false);
        setLastUpdated(new Date());
      };
      refreshRef.current = tick;
      tick();
      const id = window.setInterval(tick, SIM_TICK_MS);
      return () => window.clearInterval(id);
    }

    let cancelled = false;

    const load = async () => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setLoading(true);
      try {
        const fc = await fetchJSON<FeatureCollection<AircraftFeature>>(
          "/observations.geojson",
          { lookback_hours: lookbackHours, limit },
          controller.signal,
        );
        if (cancelled) return;
        setAircraft(fc.features ?? []);
        setError(null);
        setLastUpdated(new Date());
      } catch (err) {
        if (cancelled || (err as Error).name === "AbortError") return;
        setError((err as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    // Exposed to consumers via refresh(); captured here so the button and the
    // timer share one implementation.
    refreshRef.current = load;

    load();
    const id = window.setInterval(load, config.refreshIntervalMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
      abortRef.current?.abort();
    };
  }, [lookbackHours, limit, simulation]);

  const value: ObservationsState = {
    aircraft,
    loading,
    error,
    lastUpdated,
    simulated: simulation !== null,
    refresh: () => refreshRef.current(),
  };

  return (
    <ObservationsContext.Provider value={value}>
      {children}
    </ObservationsContext.Provider>
  );
}

export function useObservations(): ObservationsState {
  const ctx = useContext(ObservationsContext);
  if (!ctx) {
    throw new Error("useObservations must be used inside <ObservationsProvider>");
  }
  return ctx;
}
