# PR: NFZ dashboard + live map on /map

_Paste the section below into the pull request description._

---

## What this does

**`/no-fly-zone`: No-fly-zone dashboard** ("sectional chart" look)
- Readouts with 24 h sparkline, incursion timeline, zone board, filterable feed with CSV export.
- Detail panel: the detector's own explanation, an **incursion replay** of the aircraft's recorded track through the zone, and an altitude profile against the zone's floor and ceiling.
- Everything lives in the URL (`?h&sev&type&q&zone&d`), so links open exactly what you see. Keyboard shortcuts (`?` lists them). Opt-in alerts.

**`/map`: shared live map** (uses the same `LiveMap` component)
- Planes glide smoothly between 10 s updates. Trails show where each one has been, and a short vector shows where it's heading.
- Radar-style data tags placed so they don't overlap. By default only low, flagged, selected and emergency aircraft get one.
- Flight strip for the clicked aircraft, with Follow and recent detections. `?ac=<hex>` opens one directly.
- **Sky replay** (`R`): play the last hour back at 1–60×. Detections appear as they happened. "Load history" backfills the aircraft in view.
- Optional layers, **off by default**: NEXRAD weather radar, airports, navaids, day/night, incursion heatmap.
- Measure tool, aircraft search, fullscreen, folded map key.
- Spoofing and Proximity overlays are unchanged.

## Files outside `pages/nfz/` (please review)
- `src/pages/MapPage.tsx`: now renders `LiveMap`. @-mention the platform owner here. Happy to move `LiveMap` to a shared folder if preferred.
- `package.json`: `@fontsource/*` fonts; dev-only `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/dom`; `npm test`.
- `public/airspace/`: zone GeoJSON (copied from the detector fixtures). `public/context/`: OurAirports airports and navaids (public domain).

No backend changes. The API stays read-only. The frontend displays the detector's results and doesn't recompute them.

## How to test
```bash
cd frontend && npm install
npm run typecheck && npm test        # 108 tests
npm run build
```
By hand, with `docker compose up -d db api` and `npm run dev`:
- [ ] `/map`: planes move smoothly. Click one to get the flight strip and its track. Follow, Measure, and search all work.
- [ ] `/map`: Replay → Load history → play. Click a detection mark on the bar. "Live ✕" returns to live.
- [ ] `/map`: Layers → switch each context layer on and off. "Reset to calm defaults" works.
- [ ] `/no-fly-zone`: click a zone, then an incursion, then play its replay. Opening a `?d=` link selects that incursion.
- [ ] Phone width: no sideways scrolling, and the replay bar is usable.

## Notes
- Walkthrough for the team: `docs/NFZ_FRONTEND.md`.
- Replay history is kept per browser (last 60 min). A server history endpoint would make it work from first load.
- Weather tiles come from the Iowa Environmental Mesonet (NWS NEXRAD). Context data is for situational awareness only, not navigation.
