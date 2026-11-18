// Filters and the selected incursion live in the address bar, so a link like
// /no-fly-zone?h=6&zone=P-56&d=abc123 opens the page exactly as it was shared.
import { useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

export const RANGES = [
  { label: "1 hour", hours: 1 },
  { label: "6 hours", hours: 6 },
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 168 },
  { label: "30 days", hours: 720 },
] as const;
export const SEVERITIES = ["", "info", "low", "medium", "high", "critical"] as const;

export type NfzState = {
  hours: number;
  severity: string;
  zoneType: string;
  search: string;
  zone: string; // zone_id picked on the zone board
  selected: string; // detection_id open in the detail panel
};

export const DEFAULT_STATE: NfzState = { hours: 24, severity: "", zoneType: "", search: "", zone: "", selected: "" };

const KEYS: Record<keyof NfzState, string> = {
  hours: "h",
  severity: "sev",
  zoneType: "type",
  search: "q",
  zone: "zone",
  selected: "d",
};

/** Read state from URL params, ignoring anything invalid. */
export function parseState(params: URLSearchParams): NfzState {
  const h = Number(params.get(KEYS.hours));
  const sev = (params.get(KEYS.severity) ?? "").toLowerCase();
  return {
    hours: RANGES.some((r) => r.hours === h) ? h : DEFAULT_STATE.hours,
    severity: (SEVERITIES as readonly string[]).includes(sev) ? sev : "",
    zoneType: (params.get(KEYS.zoneType) ?? "").toUpperCase().slice(0, 20),
    search: (params.get(KEYS.search) ?? "").slice(0, 100),
    zone: (params.get(KEYS.zone) ?? "").slice(0, 60),
    selected: (params.get(KEYS.selected) ?? "").slice(0, 100),
  };
}

/** Write state to URL params; defaults are left out to keep links short. */
export function serializeState(state: NfzState): URLSearchParams {
  const out = new URLSearchParams();
  (Object.keys(KEYS) as (keyof NfzState)[]).forEach((k) => {
    const v = state[k];
    if (v !== DEFAULT_STATE[k] && v !== "") out.set(KEYS[k], String(v));
  });
  return out;
}

export function useNfzUrlState(): [NfzState, (patch: Partial<NfzState>) => void] {
  const [params, setParams] = useSearchParams();
  const state = useMemo(() => parseState(params), [params]);
  const update = useCallback(
    (patch: Partial<NfzState>) => {
      setParams((prev) => serializeState({ ...parseState(prev), ...patch }), { replace: true });
    },
    [setParams],
  );
  return [state, update];
}
