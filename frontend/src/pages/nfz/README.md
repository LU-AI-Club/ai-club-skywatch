# No-fly-zone frontend (NFZ team)

Everything for the `/no-fly-zone` page, the NFZ layer on the shared map, and
the live map itself (`components/LiveMap.tsx`), which both our dashboard and
the shared `/map` page (`pages/MapPage.tsx`) use. The entry points keep their
original paths: `pages/NoFlyZonePage.tsx` (the page) and
`pages/overlays/NoFlyZoneOverlay.tsx` (zones + incursions overlay).

Shared-map links: `/map?ac=<icao hex>` selects and follows an aircraft;
`/map?d=<nfz detection id>` flies to that incursion.

| Folder / file | What lives there |
|---|---|
| `format.ts` | Time and number formatting (Zulu time, "3 min ago", DMS coordinates). |
| `zones.ts` | Loading the airspace GeoJSON, zone info, schedule labels, zone outline thumbnails. |
| `altitude.ts` | Altitude parsing, altitude color bands, floor/ceiling labels. |
| `severity.ts` | Severity colors (same values as `theme.css`). |
| `trails.ts` | Building flight trails from the live feed; splitting them at gaps. |
| `geo.ts` | Small distance/bearing helpers (nautical miles). |
| `csv.ts` | CSV export of the incursion feed. |
| `flagged.ts` | Which aircraft a detector flagged recently (lock-on brackets). |
| `squawk.ts` | Emergency transponder codes (7500 / 7600 / 7700). |
| `track.ts` | Parsing `/observations/tracks` and reading positions off it (replay). |
| `urlState.ts` | Filters + selection kept in the address bar (shareable links). |
| `hooks/` | Page hooks: new-detection tracking, alerts, keyboard shortcuts, feed health, track fetch, replay clock. |
| `components/` | `LiveMap` (the shared live map), `FlightStrip`, and the page pieces: header, readouts, timeline, zone board, zone detail, feed, detail panel, altitude profile, replay controls. |
| `map/` | Leaflet layers and map controls: zones, incursions, traffic (planes, trails, tags, velocity vector, sweep paint), chart grid/rings/rose, radar sweep, HUD, legend, layer switch, aircraft search, measuring tool. |
| `__tests__/` | Unit tests for the pure helpers (`npm test`). |

Rules we follow (from the team build guide): the API stays read-only, we only
edit NFZ files, and the page shows what the detector decided instead of
re-judging it.
