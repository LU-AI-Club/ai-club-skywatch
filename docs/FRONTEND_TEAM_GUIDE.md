# SkyWatch — Team Build Guide

This is for the three detector teams: **Spoofing**, **Proximity**, and **No-fly
zone**. The shared platform is already built — the database, the API, the live
aircraft map, the navigation, and the dark theme all work. Your job is to build
**your detector's slice** of the app.

Each team builds the same three things, just for their own detector:

1. **Your API endpoint** — the data your page reads.
2. **Your dashboard page** — the page at `/<your-detector>`.
3. **Your map overlay** — how your detections show up on the shared map.

Read your AI agent this whole file plus the specific files named for your team.
Keep changes inside **your** files so three teams don't collide.

---

## How the app fits together

```
browser (React app)  ──▶  API (FastAPI, :8000)  ──▶  database
   you build your page        you tweak your endpoint      already has your table
   and map overlay
```

- The browser **never** talks to the database — only to the API.
- The API is **read-only**. It never changes data; it just hands it to the page.
- The live aircraft, the base map, the nav bar, and the theme are **done**. Don't
  rebuild them — reuse them.

## Run it locally first

You need Docker running and Node 20+.

```bash
docker compose up -d db api      # database + API on http://localhost:8000
cd frontend
npm install
npm run dev                      # the app on http://localhost:8081
```

Then open:
- `http://localhost:8081/<your-detector>` — your page (`/spoofing`, `/proximity`, `/no-fly-zone`)
- `http://localhost:8081/map` — the shared map
- `http://localhost:8000/docs` — try the API in the browser

> Note: the map is centered on **Lynchburg**. The live feed currently covers the
> **Washington D.C. area**, so live aircraft may sit off to the northeast — that's
> expected, not a bug. There's also older local data in the database you can use
> while building.

### Build and run the containers

The `api` and `frontend` are Docker images built from `api/` and `frontend/`. The
dev server above (`npm run dev`) is best for building your page — it hot-reloads.
Use the **containers** to test what actually ships (the API, and the frontend
compiled and served by nginx), or when you'd rather not install Node.

```bash
# Build and start the whole stack as containers (app on :8081, API on :8000)
docker compose up -d --build db api frontend

# Rebuild just one after you change its code:
docker compose up -d --build api        # after editing anything in api/
docker compose up -d --build frontend   # after editing anything in frontend/

# Build the images without starting them:
docker compose build api frontend

# Logs, and stopping:
docker compose logs -f api              # follow a container's logs (or: frontend)
docker compose down                     # stop everything (keeps the database)
```

- `--build` forces a fresh image; without it, `up` reuses the last build.
- **Editing `api/main.py`?** The dev server only reloads the frontend, so you must
  rebuild the api container (`docker compose up -d --build api`) for API changes to
  take effect.

## Who owns what

| Team | API endpoint | Your page file | Your table / columns |
|------|--------------|----------------|----------------------|
| **Spoofing** | `GET /spoofing-detections` | `frontend/src/pages/SpoofingPage.tsx` | `spoofing_detections` ([db/schema/002](../db/schema/002_spoofing_detections.sql)) |
| **Proximity** | `GET /proximity-detections` | `frontend/src/pages/ProximityPage.tsx` | `proximity_detections` ([db/schema/003](../db/schema/003_proximity_detections.sql)) |
| **No-fly zone** | `GET /no-fly-zone-detections` | `frontend/src/pages/NoFlyZonePage.tsx` | `no_fly_zone_detections` ([db/schema/004](../db/schema/004_no_fly_zone_detections.sql)) |

---

## 1. Your API endpoint

**File:** `api/main.py` — find your function (`spoofing_detections`,
`proximity_detections`, or `no_fly_zone_detections`).

Right now every endpoint returns **every column of your table** as JSON (the whole
row, minus the raw map geometry). It already supports these filters:
`severity`, `entity_id`, `since_hours`, `limit`, and a map bounding box.

**You only need to change this if your page needs something it doesn't already
give you.** Common reasons to edit it:

- **A filter specific to your detector.** For example, No-fly zone might add a
  `zone_type` filter; Proximity might add a "closer than X nautical miles" filter.
- **A computed field** your page wants but the table doesn't store.

Rules:
- Keep it **read-only** (a `GET` that only reads). Never write to the database.
- Your table name comes from the code, never from the user — don't build SQL out
  of user input (SQL injection).
- After editing the API, rebuild it: `docker compose up -d --build api`.

If the raw rows already have what you need, **leave the endpoint alone** and move
on to your page.

## 2. Your dashboard page

**File:** `frontend/src/pages/<YourDetector>Page.tsx` — **this page is yours.**
Design it however you like. You are not required to match the landing page's look.

**Get your data** with your hook (from `frontend/src/api/hooks.ts`):

```tsx
const { data, loading, error, reload } = useSpoofingDetections({ since_hours: 24 });
// data is an array of your detection rows — your table's columns, exactly as stored.
```

(Use `useProximityDetections` / `useNoFlyZoneDetections` for the other teams.)

**Reuse these shared components** if you want a fast start (or ignore them and
build your own):
- `DetectionTable` — a simple table of detections
- `SeverityBadge` — a colored severity label
- `StatCard` — a big number with a label
- `EmptyState` — a "nothing here" / error box

**Show what your detector already decided.** Every detection carries an `evidence`
field (and `metadata`) that explains *why* it fired, in plain language your
detector wrote. Display that — don't recompute or re-judge it on the page.

**Want live aircraft on your page too?** Call `useObservations()` — it's the same
shared live feed the map uses.

## 3. Your map overlay

**File:** `frontend/src/pages/MapPage.tsx` — the shared map with a toggle for each
detector. Today there's a **generic** overlay that just drops a dot where each
detection happened. Your job is to make **your** overlay actually show your
detector's finding well.

What a good overlay looks like per team:
- **Spoofing** — highlight the flagged aircraft and/or its track; a marker on the
  anomaly.
- **Proximity** — draw a **line between the two aircraft** in the pair, and mark
  the closest-approach point.
- **No-fly zone** — draw the **zone polygon** and mark the incursion inside it.

**How to draw anything on the map:** inside `<MapView>`, call `useLeafletMap()` to
get the raw [Leaflet](https://leafletjs.com/reference.html) map, then add your own
layers:

```tsx
const map = useLeafletMap();          // the real Leaflet map — do anything Leaflet can do
// L.polyline(...)  L.polygon(...)  L.circleMarker(...)  L.geoJSON(...)
```

Put your overlay in **your own component file** (e.g.
`frontend/src/pages/overlays/ProximityOverlay.tsx`) and have `MapPage.tsx` render
it for your toggle. That way three teams aren't editing the same block.

**No-fly zone only — the airspace polygons:** those are **not** in the API. Copy
the zone files the live detector uses from
`air/detectors/no_fly_zone/fixtures/airspace/` into `frontend/public/airspace/`,
then fetch them in your overlay and draw them with `L.geoJSON(...)`:

- `klyh-local-faa.geojson` — the 15 real FAA zones (Lynchburg-area MOAs,
  R-6602A/B/C, and P-56 over D.C.).
- `klyh-demo.geojson` — the synthetic `DEMO-1` zone, loaded when the live runner
  runs with demo zones on.

```tsx
const files = ["/airspace/klyh-local-faa.geojson", "/airspace/klyh-demo.geojson"];
for (const file of files) {
  const zones = await fetch(file).then((r) => r.json());
  L.geoJSON(zones).addTo(map);
}
```

Each feature's `properties.zone_id` matches the `zone_id` column on your
detection rows, so you can highlight the zone a detection is in. Don't use
`klyh-150nm.geojson`: it holds three made-up test zones (`P-901`, `TFR-6/1234`,
`LYNCHBURG-MOA`) that the live detector never loads, so nothing would match.

---

## What your detection rows contain

**Every detector shares these columns:**
`detection_id`, `detector_id`, `severity`, `confidence`, `entity_id` (the
aircraft, e.g. `icao24:a1b2c3`), `latitude`, `longitude`, `temporal_bounds_start`,
`temporal_bounds_end`, `last_detected_at`, and the JSON fields `evidence`,
`metadata`, `geospatial_context`, `tags`.

**Plus your own columns:**
- **Spoofing** — no extra columns; the rule that fired and the measured values
  live inside `evidence` and `metadata`.
- **Proximity** — `member_entity_ids` (both aircraft), `predicted_horizontal_nm`,
  `predicted_vertical_ft`, `t_cpa_seconds` (seconds to closest approach).
- **No-fly zone** — `zone_id`, `zone_name`, `zone_type`, `duration_seconds`.

You can read any of these straight off a row (e.g. `row.predicted_horizontal_nm`).

---

## Beyond the three deliverables (frontend extras)

The three deliverables get a basic page and overlay working. These extras are
what make it genuinely useful. The first two matter most — do them early.

### Show whether your detector is alive (important)

A page with no detections is ambiguous: is the sky quiet, or is your detector
dead? They look identical. Use `GET /detector-runs?detector_id=<your id>`
(hook: `useDetectorRuns({ detector_id: "..." })`) to show your detector's last
run — its time, its status (`RUNNING` / `SUCCESS` / `FAILED`), and its counts.
Put a small line on your page like "detector last ran 2 min ago, found 0" so an
empty table reads as *working, nothing to report* instead of *broken*.

### A detection detail view (important)

The table row and the map dot are summaries. Add a click-through — a side panel or
a modal — that shows one detection in full: its `evidence` and `metadata` (the
plain-language reason it fired, which your detector already wrote), plus the
aircraft's recent **track**. The track endpoint already exists:

```tsx
// the detection's entity_id, e.g. "icao24:a1b2c3"
GET /observations/tracks?entity_id=<entity_id>   // returns a GeoJSON line to draw
```

This is where your detector's explanation actually gets read — don't re-judge it,
just display it.

### Filter and time controls

Your page currently hardcodes the last 24 hours. Add the controls your users
actually need — a time range, a severity filter, an aircraft search. These map
straight onto the query params your endpoint already accepts (`since_hours`,
`severity`, `entity_id`, `limit`), so it's mostly wiring a dropdown to the hook.
Start with a time-range selector.

### Linking your dashboard and the map

This connects your two views so they feel like one app, and it is **different from
the overlay**:

- **The overlay** (deliverable 3) draws *all* your recent detections on the
  `/map` page — the spatial picture, everything at once.
- **Linking** is about *one* detection at a time: click a row in your dashboard →
  open the map focused on that detection with its aircraft highlighted; click a dot
  on the map → open its details. It needs a shared "selected detection" between the
  two pages.

Build the overlay first; linking is polish on top of it.

### Making the overlay feel live

Detections are **events, not moving dots** — so "live" means "recently fired."
Poll your endpoint with a short window (e.g. `since_hours=1`) on a timer and
redraw, letting old detections age out. The best version doesn't just drop a
static dot: it finds the matching **live aircraft** (same `entity_id`) and lights
*it* up — a colored ring or pulse — and falls back to the detection's own
`latitude`/`longitude` when that aircraft has already left the live window. The
aircraft feed and its refresh timer are already shared (`useObservations()`), so
you're adding a detection layer on top, not a second map. Remember: the overlay is
only ever as live as your detector is actually running.

## Ground rules (so three teams don't collide)

- **Edit only your files:** your endpoint function in `api/main.py`, your
  `*Page.tsx`, and your own overlay component. Coordinate before touching anything
  shared.
- **Don't edit** the shared pieces unless you've agreed to: `src/map/MapView.tsx`,
  `src/api/client.ts`, `src/components/`, `src/theme.css`, `src/App.tsx`, `Nav.tsx`.
- Keep the **API read-only**.
- Show your detector's **own explanation**; don't recompute detections on the page.

## Pointing your AI agent at this

Give your agent: **this file**, your `*Page.tsx`, `frontend/src/api/hooks.ts`
(so it knows your data hook), and your table's schema file from the table above.
For map work, also give it `frontend/src/pages/MapPage.tsx` and
`frontend/src/map/MapView.tsx`. Tell it to stay inside your files and keep the API
read-only.
