// Runtime config, resolved in the browser (mirrors SENTINEL's sentinel-config.js).
// Loaded by index.html BEFORE the app, so the same build runs in any environment:
// edit this file (or mount a different one) to point at a different API.
(function () {
  const existing = window.SKYWATCH_CONFIG || {};
  const loc = window.location;
  const isHttp = loc.protocol === "http:" || loc.protocol === "https:";
  // When the app is served from the Vite dev port or the demo gateway, the API
  // is a separate origin on :8000. Otherwise assume API and UI share an origin.
  const localFrontend = isHttp && ["5173", "8081", "8090"].includes(loc.port);
  const defaultApiBaseUrl =
    isHttp && !localFrontend ? loc.origin : "http://localhost:8000";

  window.SKYWATCH_CONFIG = {
    apiBaseUrl: defaultApiBaseUrl,
    // Lynchburg (KLYH) — the club's home airspace.
    mapCenter: [37.33, -79.2],
    mapZoom: 9,
    // One shared refresh timer drives every live view (see src/api/observations.tsx).
    refreshIntervalMs: 10000,
    // How far back the live aircraft view looks (hours). 1 = "live"; widen it to
    // show recent history, or a dataset whose newest rows are older than an hour.
    observationsLookbackHours: 1,
    // Dark basemap, no API key required (Esri dark gray canvas).
    tileUrl:
      "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    tileAttribution: "Tiles &copy; Esri",
    ...existing,
  };
})();
