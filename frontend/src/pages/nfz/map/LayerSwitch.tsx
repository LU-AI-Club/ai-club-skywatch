// Layer switches + fullscreen, top-right of the live map, grouped so the
// menu stays tidy. Calm by default: context layers start off. Choices are
// remembered in this browser.
import { useState, type ReactNode } from "react";

export type TagMode = "key" | "all" | "off";
export type MapLayers = {
  traffic: boolean;
  trails: boolean;
  tags: TagMode;
  chart: boolean;
  sweep: boolean;
  weather: boolean;
  airports: boolean;
  navaids: boolean;
  daynight: boolean;
  heatmap: boolean;
};

export const DEFAULT_LAYERS: MapLayers = {
  traffic: true,
  trails: true,
  tags: "key",
  chart: true,
  sweep: true,
  weather: false,
  airports: false,
  navaids: false,
  daynight: false,
  heatmap: false,
};

const STORAGE_KEY = "skywatch.nfz.layers";

/** Read saved choices; older saves (tags as true/false) are upgraded. */
export function parseLayers(raw: string | null): MapLayers {
  if (!raw) return DEFAULT_LAYERS;
  try {
    const saved = JSON.parse(raw) as Partial<Omit<MapLayers, "tags">> & { tags?: unknown };
    const tags: TagMode = saved.tags === "all" || saved.tags === "off" || saved.tags === "key" ? saved.tags : saved.tags === false ? "off" : "key";
    const out = { ...DEFAULT_LAYERS };
    for (const k of Object.keys(DEFAULT_LAYERS) as (keyof MapLayers)[]) {
      if (k !== "tags" && typeof saved[k] === "boolean") (out[k] as boolean) = saved[k] as boolean;
    }
    return { ...out, tags };
  } catch {
    return DEFAULT_LAYERS;
  }
}

export function loadLayers(): MapLayers {
  try {
    return parseLayers(window.localStorage.getItem(STORAGE_KEY));
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

type Toggle = { key: Exclude<keyof MapLayers, "tags">; label: string; hint?: string };
const GROUPS: { title: string; items: Toggle[] }[] = [
  {
    title: "Traffic",
    items: [
      { key: "traffic", label: "Aircraft" },
      { key: "trails", label: "Trails" },
    ],
  },
  {
    title: "Chart",
    items: [
      { key: "chart", label: "Grid, rings & rose" },
      { key: "sweep", label: "Radar sweep" },
    ],
  },
  {
    title: "Context",
    items: [
      { key: "weather", label: "Weather radar", hint: "NEXRAD, updates every 5 min" },
      { key: "airports", label: "Airports" },
      { key: "navaids", label: "Navaids", hint: "VOR · NDB" },
      { key: "daynight", label: "Day / night" },
      { key: "heatmap", label: "Incursion heatmap" },
    ],
  },
];

const TAG_MODES: { mode: TagMode; label: string; title: string }[] = [
  { mode: "key", label: "Key", title: "Selected, flagged, emergencies, and aircraft below 5,000 ft" },
  { mode: "all", label: "All", title: "Every aircraft (when zoomed in)" },
  { mode: "off", label: "Off", title: "Only on hover, plus selected, flagged and emergencies" },
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
  /** Extra controls at the start of the bar (search, measure, replay). */
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const extras = GROUPS[2].items.filter((t) => layers[t.key]).length;
  return (
    <div className="nfz-layers">
      <div className="nfz-layers-bar">
        {children}
        <button className="nfz-mapbtn" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          Layers{extras ? <span className="nfz-mapbtn-badge">{extras}</span> : null} {open ? "▴" : "▾"}
        </button>
        <button className="nfz-mapbtn" onClick={onFullscreen} title="Fullscreen (F · Esc to exit)">
          {isFull ? "Exit full" : "Fullscreen"}
        </button>
      </div>
      {open && (
        <div className="nfz-layers-panel">
          {GROUPS.map((g) => (
            <fieldset key={g.title}>
              <legend>{g.title}</legend>
              {g.items.map((t) => (
                <label key={t.key} title={t.hint}>
                  <input type="checkbox" checked={layers[t.key]} onChange={(e) => onChange({ ...layers, [t.key]: e.target.checked })} />
                  <span>{t.label}</span>
                  {t.hint && <em>{t.hint}</em>}
                </label>
              ))}
              {g.title === "Traffic" && (
                <div className="nfz-seg" role="radiogroup" aria-label="Data tags">
                  <span>Data tags</span>
                  {TAG_MODES.map((m) => (
                    <button
                      key={m.mode}
                      role="radio"
                      aria-checked={layers.tags === m.mode}
                      className={layers.tags === m.mode ? "is-on" : undefined}
                      title={m.title}
                      onClick={() => onChange({ ...layers, tags: m.mode })}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              )}
            </fieldset>
          ))}
          <button className="nfz-layers-reset" onClick={() => onChange(DEFAULT_LAYERS)}>
            Reset to calm defaults
          </button>
        </div>
      )}
    </div>
  );
}
