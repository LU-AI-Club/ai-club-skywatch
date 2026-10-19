# Local SkyWatch database

A one-container Postgres (TimescaleDB + PostGIS) with the canonical
`observations` table and the three air detection tables. This is what lets you
populate observations on your own machine, run the detectors against a real
database, and host a front end locally — **without** the full SENTINEL platform
and **without** the company-confidential platform repo.

It mirrors the shape of the real platform (`observations` is vendored faithfully;
the detection tables are the air analogues of the maritime ones), so code written
against this local DB moves to production unchanged.

## Start it

From the repo root:

```bash
docker compose up -d db
```

First boot creates the schema from [`db/schema/`](schema/) automatically. Connect
from your host (detectors, `psql`, a dashboard) with:

```
postgresql://skywatch:skywatch@localhost:5432/skywatch
```

Stop it (keeps your data):

```bash
docker compose down
```

Wipe it and force a fresh schema load (do this after changing any `.sql`):

```bash
docker compose down -v && docker compose up -d db
```

## What's in it

| Object | Purpose |
| --- | --- |
| `observations` | Canonical input. ADS-B rows have `domain = 'air'`, `entity_id = 'icao24:<hex>'`, position in `location`, speed/track in `sog`/`cog`; **altitude, callsign, squawk, NIC, NACp live in the `payload` JSON**. Vendored copy of the platform table — keep in sync. |
| `adsb_spoof_detections` | `skywatch.spoofing` output. |
| `adsb_proximity_detections` | `skywatch.proximity` output (one row per aircraft pair). |
| `airspace_violation_detections` | `skywatch.no_fly_zone` output (one row per incursion episode). |
| `detector_runs` | Optional heartbeat: one row per detector run. |

Each detection table shares one base column set and is upserted on `dedup_key`
(the string form of `air.windowing.detection_dedup_key`), so re-running a detector
over the same data updates rows in place instead of duplicating them.

## Populate `observations`

Two routes, same normalizer underneath:

1. **Direct CSV → Postgres (local dev).** A small loader reads a recorded
   `aircraft.json`/`data/lynchburg_adsb.csv` and inserts rows with `domain = 'air'`.
   No Kafka needed. Inserts must fill the `NOT NULL` columns `location`,
   `h3_index_res7/9` (compute with the `h3` library) and `provenance_id`.
2. **Full pipeline (mirrors production).** antenna → gateway → `adsb.raw` Kafka →
   the `adsb-loader` → `observations`. Heavier; the Tech Lead runs this.

See [`docs/SENTINEL_INTEGRATION_PLAN.md`](../docs/SENTINEL_INTEGRATION_PLAN.md) for
how this fits the whole integration and the 6-week plan.

## Notes

- **Config:** defaults (user/password/db `skywatch`, port 5432) are set in
  [`docker-compose.yml`](../docker-compose.yml); override with a `.env` file or
  environment variables if 5432 is taken.
- **Resources:** the image is ~1 GB on first pull and wants a couple of GB of RAM
  — fine for Docker Desktop on Windows/Mac.
- **Provisional names:** the detection table names/columns are provisional until
  confirmed with Xenith. The Tech Lead owns these migrations into the platform;
  keep this `db/schema/` and the platform's `db/schema/` in lockstep once agreed.
- **Airspace zones** for the no-fly-zone detector come from GeoJSON files, not a
  database table, so the maritime `risk_zones` table is intentionally not here.
