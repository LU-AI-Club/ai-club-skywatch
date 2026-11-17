# SkyWatch frontend

A React (Vite + React Router + Leaflet) single-page app over the SkyWatch API.
Dark theme, one integrated app: a landing page, a shared live map, and one
dashboard page per detector team. See `docs/FRONTEND_PLAN.md` for the full plan.

## Run it

Needs Node 20+. The API should be running (`docker compose up -d db api`).

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:8081. The app resolves the API at http://localhost:8000
via `public/skywatch-config.js` (edit that file to point elsewhere).

Build the production bundle, or serve it in a container:

```bash
npm run build                      # outputs to dist/
docker compose up -d --build frontend   # nginx serves dist/ on :8081
```

`npm run typecheck` runs TypeScript (the build itself uses esbuild and does not
fail on type errors, so types are advisory — handy, not a gate).

## Layout

```
public/skywatch-config.js   runtime config (apiBaseUrl, map center, tiles, refresh)
src/config.ts               typed view of that config
src/api/                    client, types, hooks
  observations.tsx          ONE shared refresh timer -> useObservations()
  hooks.ts                  useSpoofingDetections() / useProximityDetections() / ...
  types.ts                  AircraftFeature (typed) + Detection (team-owned shape)
src/map/MapView.tsx         shared Leaflet map; owns aircraft layer; exposes raw map
src/map/mapContext.ts       useLeafletMap() -> the raw L.Map
src/components/              Nav, DetectionTable, SeverityBadge, StatCard, EmptyState
src/pages/
  Landing.tsx               club / semester landing (shared design)
  MapPage.tsx               live map + detector overlay toggles (shared design)
  SpoofingPage.tsx          \
  ProximityPage.tsx          }  TEAM-OWNED — design freely
  NoFlyZonePage.tsx         /
```

## For the three teams

Your page (`src/pages/<Detector>Page.tsx`) is **yours**. Design it however you
like — you are not bound by the landing page's look. The scaffold gives you:

- **Your data:** `use<Detector>Detections(params)` returns your rows exactly as
  the database stores them. The shape is yours — add columns to your table and
  they appear on the row automatically; no frontend change needed.
- **The map:** render `<MapView>` and call `useLeafletMap()` inside it to get the
  raw Leaflet map. Do anything Leaflet can do.
- **Live aircraft:** `useObservations()` gives the shared live feed (one timer,
  app-wide) — the same aircraft the map shows.

The shared theme, components, and nav are a starting point, not a requirement.
