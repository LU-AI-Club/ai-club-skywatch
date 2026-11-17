// Typed view over window.SKYWATCH_CONFIG (set by public/skywatch-config.js).
// Falls back to sane dev defaults if that script did not load.
export interface SkywatchConfig {
  apiBaseUrl: string;
  mapCenter: [number, number];
  mapZoom: number;
  refreshIntervalMs: number;
  observationsLookbackHours: number;
  tileUrl: string;
  tileAttribution: string;
}

const fallback: SkywatchConfig = {
  apiBaseUrl: "http://localhost:8000",
  mapCenter: [37.33, -79.2],
  mapZoom: 9,
  refreshIntervalMs: 10000,
  observationsLookbackHours: 1,
  tileUrl:
    "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
  tileAttribution: "Tiles &copy; Esri",
};

declare global {
  interface Window {
    SKYWATCH_CONFIG?: Partial<SkywatchConfig>;
  }
}

export const config: SkywatchConfig = { ...fallback, ...(window.SKYWATCH_CONFIG ?? {}) };
