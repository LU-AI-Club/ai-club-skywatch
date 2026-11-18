// Layer switches + fullscreen, top-right of the dashboard map. The choices
// are remembered in this browser.
import { useState, type ReactNode } from "react";

export type MapLayers = { traffic: boolean; trails: boolean; tags: boolean; chart: boolean; sweep: boolean };

export const DEFAULT_LAYERS: MapLayers = { traffic: true, trails: true, tags: true, chart: true, sweep: true };

const STORAGE_KEY = "skywatch.nfz.layers";

export function loadLayers(): MapLayers {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? { ...DEFAULT_LAYERS, ...(JSON.parse(raw) as Partial<MapLayers>) } : DEFAULT_LAYERS;
  } catch {
    return DEFAULT_LAYERS;
  }
}
export function saveLayers(l: MapLayers): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(l));
  } catch {
    /* storage unavailable: the choice just won't be remembered */
  }
}

const LABELS: [keyof MapLayers, string][] = [
  ["traffic", "Aircraft"],
  ["trails", "Trails"],
  ["tags", "Data tags (zoomed in)"],
  ["chart", "Grid, rings & rose"],
  ["sweep", "Radar sweep"],
];

export function LayerSwitch({
  layers,
  onChange,
  isFull,
  onFullscreen,
  children,
}: {
  layers: MapLayers;
  onChange: (l: MapLayers) => void;
  isFull: boolean;
  onFullscreen: () => void;
  /** Extra controls at the start of the bar (the aircraft search). */
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="nfz-layers">
      <div className="nfz-layers-bar">
        {children}
        <button className="nfz-mapbtn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          Layers {open ? "▴" : "▾"}
        </button>
        <button className="nfz-mapbtn" onClick={onFullscreen} title="Fullscreen (F · Esc to exit)">
          {isFull ? "Exit full" : "Fullscreen"}
        </button>
      </div>
      {open && (
        <div className="nfz-layers-panel">
          {LABELS.map(([key, label]) => (
            <label key={key}>
              <input
                type="checkbox"
                checked={layers[key]}
                onChange={(e) => onChange({ ...layers, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
