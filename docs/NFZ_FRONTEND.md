# NFZ frontend walkthrough

How the No-fly-zone dashboard and the shared live map work, written for
teammates picking this up (and for anyone new to React or Leaflet). For a
file-by-file list, see [`frontend/src/pages/nfz/README.md`](../frontend/src/pages/nfz/README.md).

**The two-minute version.** The browser never talks to the database. It asks
the read-only API for three things: live aircraft (`/observations.geojson`,
every 10 s), detections (`/no-fly-zone-detections` and the other detectors),
and one aircraft's path (`/observations/tracks`). Zone shapes, airports and
navaids are static files in `frontend/public/`. One React component,
`LiveMap`, draws the map for both the `/no-fly-zone` dashboard and the shared
`/map` page. Everything on the map is a small "layer" component in
`pages/nfz/map/`.

---

## 1. Run it

```bash
docker compose up -d db api            # database + API on :8000
cd frontend
npm install
npm run dev                            # the app on :8081
npm test                               # 108 unit + component tests
npm run typecheck                      # TypeScript
```

Pages: `localhost:8081/no-fly-zone` (our dashboard) and `localhost:8081/map`
(the shared map).

## 2. The big picture

```
API (read-only)                    browser
───────────────                    ───────────────────────────────────────────────
/observations.geojson ──10 s──▶ useObservations() ─┐  (one shared timer for the app)
/no-fly-zone-detections ─30 s─▶ useNoFlyZoneDetections()
/observations/tracks ──on demand──▶ useTrack(), "Load history", click-a-plane
public/airspace/*.geojson ───────▶ useZones()
public/context/*.geojson ────────▶ airports / navaids layers (only if switched on)

NoFlyZonePage ──▶ header, readouts, timeline, zone board, feed, detail panel
      │                                         └─ DetailPanel: incursion replay + altitude profile
      └──▶ AirspaceMap ──▶ LiveMap ◀── MapPage (/map) also uses LiveMap
                               │
                               ├─ TrafficLayer   planes, trails, tags, follow, sweep paint
                               ├─ ChartLayer     grid, range rings, compass rose
                               ├─ context layers weather, airports, navaids, day/night, heatmap
                               ├─ MapHud, LayerSwitch, AircraftSearch, MeasureTool, MapLegend
                               ├─ FlightStrip    the selected aircraft
                               ├─ ReplayBar      sky replay (only while replaying)
                               └─ children       detector overlays (NoFlyZoneOverlay, Spoofing, Proximity)
```

**Rule we follow everywhere:** the frontend shows what the detector decided.
It never re-judges an incursion. The altitude profile, the zone "schedule"
label and the lock-on brackets only display data that already exists.

## 3. How a map layer works

Every layer follows the same small pattern, so once you've read one you can
read them all:

```tsx
export function ExampleLayer({ points }: { points: { lat: number; lon: number }[] }) {
  const map = useLeafletMap();               // the real Leaflet map (from <MapView>)
  useEffect(() => {
    if (!map) return;                         // not mounted yet
    const layer = L.layerGroup().addTo(map);  // 1. make a group and add it
    for (const p of points) L.circleMarker([p.lat, p.lon]).addTo(layer); // 2. draw
    return () => { layer.remove(); };         // 3. clean up when props change or the layer unmounts
  }, [map, points]);
  return null;                                // draws on the map, not in React's DOM
}
```

Step 3 matters: without it, every redraw stacks another copy on the map.

**Stacking order.** We use our own Leaflet "panes" (`map/panes.ts`) so layers
stack sensibly no matter what order they're added in:

| z-index | What |
|---|---|
| 200 | basemap tiles (Leaflet) |
| 240 / 245 | weather radar / night shading |
| 250 | chart grid, rings, rose |
| 380 | heatmap |
| 390 | trails (canvas) |
| 400 | zones, incursion markers (Leaflet's overlay pane) |
| 450 | labels, airports, navaids |
| 600 | planes (Leaflet's marker pane) |
| 1000 | HUD, buttons, legend, flight strip, replay bar |

**Styling.** Map CSS is in `map/map.css`, page CSS in `nfz.css`. Every class
starts with `nfz-` so nothing leaks onto the other teams' pages.

## 4. Live traffic (`map/TrafficLayer.tsx`)

- **The feed updates every 10 s**, but planes don't jump: between updates each
  plane *glides* along its course at its speed (dead reckoning), capped at
  20 s past its last real position.
- **History is recorded in the browser** (`trails.ts`). The API only returns
  each aircraft's newest position, so every update is appended to a store
  that keeps the last 60 minutes. Trails draw the last few minutes of it,
  shorter when you zoom in so they stay about the same length on screen.
- **Data tags** (callsign / altitude in hundreds of feet with ↑↓ / speed)
  appear when zoomed in. `map/labels.ts` places them like a radar display:
  each tag tries four spots around its plane, keeps last second's spot if it
  still fits, and hides if nothing fits. Selected, flagged and emergency
  aircraft always keep their tag.
- **Visual hierarchy:** planes above FL180 (higher than any of our zones) are
  smaller and dimmer; emergency squawks (7500/7600/7700) are red; aircraft a
  detector flagged recently get lock-on brackets.
- **Radar sweep:** `SweepLayer.tsx` turns the beam; TrafficLayer lights up the
  planes it just passed. Only planes whose glow changed are touched, and the
  glow filter only runs while lit (filters are expensive with hundreds of
  planes).

## 5. Sky replay (`replay.ts`, `hooks/useSkyReplay.ts`, `components/ReplayBar.tsx`)

Press **Replay** (or `R`). The bar plays the last hour back at 1×–60×.

- Positions come from the browser's recorded history, interpolated between
  fixes (`aircraftAt`). A plane that drops out of the feed is held briefly at
  its last real position, never slid across the gap.
- The lighter band on the bar shows how much history this browser has. **Load
  history** fetches the last hour of track for up to 80 aircraft in view
  (4 at a time) to fill it in.
- Overlays read the replay moment from `ReplayContext`, so incursion markers
  and "hot" zones appear only once they've happened. The small marks on the
  bar are detections; click one to jump 30 s before it.
- Not the same thing as the **incursion replay** in the dashboard's detail
  panel, which replays one aircraft's recorded track through one zone, with
  the altitude profile.

## 6. The dashboard (`NoFlyZonePage.tsx`)

- **Everything is in the URL** (`urlState.ts`): time range, severity, zone
  type, search, selected zone (`zone=`) and selected incursion (`d=`). Copy
  the address bar to share exactly what you see.
- **Zone board:** click a zone to filter, open its details and fly the map to
  it. Clicking a zone on the map does the same.
- **Detail panel:** detector's explanation, incursion replay with the
  altitude profile (zone floor–ceiling band, IN/OUT window), facts, raw
  evidence. "Follow live on main map" opens `/map?ac=<hex>`.
- **Shortcuts:** `J`/`K` step through the feed, `Esc` closes, `F` fullscreen,
  `R` sky replay, `/` search, `?` the list.
- **Alerts** are opt-in (sound, notification and a tab-title count for new
  HIGH/CRITICAL incursions).

## 7. Calm by default

The map can show a lot, so it starts quiet and lets you add detail. When you
add something, keep to these:

1. **New layers start off.** Put them in the right group in `LayerSwitch.tsx`
   (Traffic / Chart / Context) and add a legend row that only shows while the
   layer is on.
2. **Don't add tags or labels for everything.** Show them for what matters
   (low, flagged, selected) and let hover reveal the rest.
3. **Fade what's less relevant** rather than removing it (high traffic,
   old trail segments).
4. **Controls appear when used** (the replay bar, the measure readout).
5. **Respect reduced motion:** animations sit inside
   `@media (prefers-reduced-motion: no-preference)`.

## 8. Testing

- **Unit tests** (`__tests__/*.test.ts`) cover the pure helpers: time and
  number formatting, zones, altitude, trails and climb rate, replay
  interpolation, tag placement, sun position, CSV export (including blocking
  spreadsheet formulas), URL state, saved layer settings.
- **Component tests** (`__tests__/components/*.test.tsx`) render real React
  components in a simulated browser (jsdom + Testing Library): timeline, zone
  board, feed table and filters, readouts, layer menu, replay bar, flight
  strip, shortcut help.
- **Not covered automatically:** anything that draws on the Leaflet map
  (canvas, SVG, tiles) needs a real browser. Before a PR, check by hand:
  - `/map`: planes move smoothly; click one (flight strip + track); Follow;
    Measure; Replay → Load history → play; each context layer on and off.
  - `/no-fly-zone`: click a zone, an incursion, play its replay; `?d=` links
    open the right incursion; phone width doesn't overflow.

## 9. Shared files we touched (talk to the platform team)

The build guide asks teams to stay inside their own files. These changes go
outside `pages/nfz/` and need a heads-up before merging:

- **`pages/MapPage.tsx`**: now renders `LiveMap` (the Spoofing and Proximity
  overlays are unchanged). The platform team may prefer `LiveMap` and the
  generic map pieces moved to a shared folder; that's a file move, nothing more.
- **`package.json`**: fonts (`@fontsource/*`) and test tools (`vitest`,
  `jsdom`, `@testing-library/*`), plus `npm test`.
- **`public/airspace/`, `public/context/`**: static data files.

## 10. Data sources

| What | Source |
|---|---|
| Zones | `air/detectors/no_fly_zone/fixtures/airspace/` (copied to `public/airspace/`) |
| Airports, navaids | [OurAirports](https://ourairports.com/data/), public domain (`public/context/`) |
| Weather radar | NWS NEXRAD mosaic via the [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/ogc/) tile service |
| Basemap | Esri World Dark Gray (configured by the platform team) |

Context data is for situational awareness, not navigation.

## 11. Known limits and ideas

- History for replay is per browser: open the map and it starts recording;
  "Load history" backfills only what's in view (up to 80 aircraft).
- Spoofing/Proximity overlays on `/map` aren't replay-aware yet (they could
  read `useReplayAt()` the same way ours do).
- The compass rose points to true north; real charts align roses to magnetic
  north (about 9° different here).
- Ideas: a shared history endpoint for replay, per-team colors in the HUD,
  and moving `LiveMap` to a platform-owned folder.
