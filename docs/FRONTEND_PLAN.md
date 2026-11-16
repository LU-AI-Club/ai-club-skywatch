# SkyWatch Frontend Plan

Status: approved design, build in progress (API first).
Owner: platform (Nate + Claude). Audience: the three detector teams.

This is the plan for the SkyWatch web app the club builds together. It is
modeled on the Xenith SENTINEL platform's web stack, adapted for an AI-club
project: **a database the detectors already write to, an HTTP API over that
database, and a browser app that only ever talks to the API.** The frontend
never touches the database directly.

```
browser (React SPA)  ──HTTP/JSON──▶  api (FastAPI :8000)  ──psycopg pool──▶  db (Postgres/Timescale/PostGIS)
     Leaflet map                       read-only                               observations + *_detections
```

---

## 1. What already exists (do not rebuild)

- **`db`** — Timescale + PostGIS, schema in `db/schema/`:
  `observations` (ADS-B rows, `domain='air'`), `spoofing_detections`,
  `proximity_detections`, `no_fly_zone_detections`, `detector_cursors`,
  `detector_runs`.
- **Detector runners + live ADS-B poller** (`scripts/poll_adsb_feed.py`) — these
  populate the tables above. The live feed writes the SENTINEL envelope into
  `observations.payload` (`payload.payload.*`, raw readsb names).
- **A Streamlit NFZ dashboard** (`air/detectors/no_fly_zone/dashboard/`) — a
  separate, file-based tool. It is **not** part of this web app and is not the
  model here. Keep it or retire it independently.

The data layer is done. The missing layer is the HTTP API over it, and the app
that consumes it. That is what this plan builds.

---

## 2. Architecture decisions (locked)

| # | Decision | Choice |
|---|----------|--------|
| API | Shape | Read-only. One endpoint per detector. Teams own their detection envelope — the API returns detection rows close to raw. |
| API | Conventions | Query params, units, and GeoJSON property shape follow `xenith-sentinel-platform/frontend/ais_map.html` (knots, degrees, ISO `observed_at`, `position_age_hours`, bbox params, `limit`). |
| API | Airspace/zones | **Not** an API endpoint. The NFZ page fetches the static airspace GeoJSON (`air/detectors/no_fly_zone/fixtures/airspace/*.geojson`) directly. |
| API | Auth | None. No trust/clearance headers (those are SENTINEL-specific). |
| Frontend | Framework | **React** (Vite + React Router). "Flashy," integrated single app. |
| Frontend | Map | **Leaflet**, dark basemap (CartoDB dark_all tiles — no API key). |
| Frontend | Config | One central runtime config (`skywatch-config.js`) that resolves `apiBaseUrl` from `window.location`, mirroring `sentinel-config.js`. Same ports as SENTINEL: frontend `:8081`, API `:8000`. No per-page overrides. |
| Frontend | Shared map module | Owns the base map + aircraft layer + **one shared refresh timer**. Hands teams the raw Leaflet `map` object for maximum flexibility (no plugin framework). |
| Frontend | Theme | Dark, single theme. Accent: **Circuit cyan** (`#22D3EE`) — echoes the logo's circuit traces, stays clear of the severity color scale. One-token swap if we change it. |

### Consequence of choosing React
SENTINEL's frontend is zero-build static HTML served by nginx. React adds a
**build step**: Vite dev server in development; `vite build` → `dist/` served by
nginx in the container. The container model survives; it just gets a build stage.

---

## 3. Page map (integrated app, client-side routing)

| Route | Page | Owner | Notes |
|-------|------|-------|-------|
| `/` | Landing — AI club + semester work | platform | Shared shell/theme. |
| `/spoofing` | Spoofing dashboard | **Spoofing team** | Team-owned canvas. |
| `/proximity` | Proximity dashboard | **Proximity team** | Team-owned canvas. |
| `/no-fly-zone` | No-fly-zone dashboard | **NFZ team** | Team-owned canvas. Also fetches static airspace GeoJSON. |
| `/map` | Shared aircraft map | platform | Live aircraft; toggleable per-detector overlay modes. |

**Detector pages are each team's own canvas.** Teams may design them however they
like and are free to stray from the landing page's look. The shared theme,
components, and API hooks are a *starting point*, not a requirement, on those
three pages. The landing page, the nav, and the map page carry the shared design.

Teams have minimal frontend experience but will use AI coding agents, so the
scaffold optimizes for clean seams: a route, a mounting point, a typed API hook
(`useSpoofingDetections()` etc.), and optional shared components — all documented
per page so an agent has an obvious place to work.

---

## 4. The four pre-meeting deliverables (platform builds these first)

1. **API service** (`api/`) — FastAPI, read-only, over the existing DB.
   **← in progress, this is the critical path.** Contract in §5.
2. **Runtime config** (`skywatch-config.js`) — `apiBaseUrl` resolution, dark tile
   URL, default map center/zoom, shared refresh interval.
3. **Shared map module** — React + Leaflet. Base map + aircraft layer + shared
   refresh timer; exposes the raw `map` instance and the observations data.
4. **App shell + theme + components** — React Router, dark theme tokens, nav,
   landing + map pages, and a small kit (detection table, detail panel, severity
   badge, stat cards, empty-state) teams may use or ignore.

The API is built first because every team page and the map are coded against it.

---

## 5. API contract

Base URL resolves to `http://localhost:8000` in local dev. All endpoints are
`GET`, read-only, and return JSON (GeoJSON where noted). CORS is open in dev.

### Aircraft / observations

- **`GET /observations.geojson`** — newest position per aircraft.
  Query: `lookback_hours` (default 1), `limit` (default 1000, max 5000),
  `min_lat`/`min_lon`/`max_lat`/`max_lon` (bbox, optional), `hex` (exact ICAO),
  `callsign` (substring, case-insensitive).
  Returns a GeoJSON `FeatureCollection` of `Point`s. Feature `id` = ICAO hex.
  Properties: `icao24`, `callsign`, `altitude`, `squawk`, `category`,
  `sog` (kn), `cog` (°), `heading` (°), `latitude`, `longitude`, `observed_at`
  (ISO), `position_age_hours`, `source_id`.
  Handles both `payload` shapes (flat CSV + live readsb envelope) via `COALESCE`.

- **`GET /observations/tracks`** — one aircraft's recent path.
  Query: `entity_id` (required; `icao24:xxxxxx` or bare hex), `lookback_hours`
  (default 6), `limit` (default 2000). Returns a `FeatureCollection` with one
  `LineString` (ordered oldest→newest) and `properties.points[]` carrying per-fix
  metadata.

### Detections (one endpoint per detector — teams own the shape)

- **`GET /spoofing-detections`**
- **`GET /proximity-detections`**
- **`GET /no-fly-zone-detections`**

Each returns a JSON array of detection rows as stored (the full envelope —
shared columns *and* detector-specific columns — minus the raw `position`
geometry, which is redundant with `latitude`/`longitude`). Because the API emits
`to_jsonb(row)`, any column a team adds later flows through automatically; no API
change needed.
Query (all optional): `severity`, `entity_id`, `since_hours`
(filters `last_detected_at`), `limit` (default 500, max 5000),
`min_lat`/`min_lon`/`max_lat`/`max_lon` (bbox). Ordered by `last_detected_at`
descending (most recently active first).

### Health / liveness

- **`GET /health`** — process up.
- **`GET /health/db`** — DB reachable (runs `SELECT 1`).
- **`GET /detector-runs`** — recent detector-run rows (status, counts, timings) so
  the UI can show whether a detector is alive. Query: `detector_id` (optional),
  `limit` (default 50). A quiet sky and a dead detector look identical without
  this.

---

## 6. Theme

Logo is monochrome (white eagle + circuit traces on black), so the base is
white-on-near-black and the accent is a design choice:

- Page `#0A0A0C`, surface `#141418`, raised `#1C1C22`, border `#2A2A32`
- Text `#F4F4F6`, muted `#9A9AA5`
- Accent (brand/interactive): **Circuit cyan `#22D3EE`** (hover `#0891B2`)
- Severity scale (shared, used for all detections, independent of the accent):
  info `#3B82F6`, low `#10B981`, medium `#F59E0B`, high `#F97316`,
  critical `#EF4444`

Optional: each team page may take its own accent for identity (e.g. proximity
cyan, spoofing violet, NFZ amber-as-chrome) while severity colors stay constant
everywhere.

---

## 7. Open items

- **Landing page copy** — the club's semester-work writeup (platform/Nate).
- **Palette** — defaulted to Circuit cyan; change is one token.
- Items 2–4 (config, map module, shell) are built after the API lands.
