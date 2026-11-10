# Running the SkyWatch live pipeline

End-to-end: the **poller** pulls live ADS-B from the Xenith feed into the
`observations` table, and the **detector runners** read that table, run the
detectors, and write to the detection tables.

```
Xenith ADS-B feed --> adsb-poller --> observations (Postgres) --> detector runner --> <detector>_detections
```

All commands run from the repo root. The database is reachable from your host at
`postgresql://skywatch:skywatch@localhost:5432/skywatch`.

## Prerequisites

- **Docker Desktop** running.
- The SENTINEL CA cert at the repo root as `sentinel-ca.crt` (the poller mounts it
  read-only to verify TLS to the feed). Override the path with
  `SKYWATCH_ADSB_CA_FILE` if it lives elsewhere.
- Network access to the feed host (`adsb-ingest.sentinel.xenithsolutions.com`) —
  your machine must be whitelisted.
- Pass `--build` whenever you've changed Python under `air/` or `scripts/` — the
  containers run baked-in code, not your working tree.

---

## 1. Start the database and poller

```bash
docker compose --profile poller up -d --build db adsb-poller
```

Confirm both are up (db should say `healthy`):

```bash
docker compose ps
```

Watch the poller pull (look for `poll ok: features=… inserted=…`):

```bash
docker logs --tail 10 -f skywatch-adsb-poller
```

---

## 2. Check the database is populating

Row count, distinct aircraft, and how fresh the newest row is (`staleness` should
be seconds, and `rows` should grow between runs):

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -c "SELECT count(*) AS rows, count(DISTINCT entity_id) AS aircraft, max(observed_at) AS latest, (now() - max(observed_at)) AS staleness FROM observations WHERE domain='air';"
```

What one observation row looks like (typed columns the detectors read):

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -x -c "SELECT entity_id, observed_at, ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon, sog, cog, raw_record_ref FROM observations WHERE domain='air' ORDER BY observed_at DESC LIMIT 1;"
```

The raw ADS-B data lives in the `payload` JSON (the SENTINEL envelope; the readsb
fields are nested under `payload.payload`):

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -tAc "SELECT jsonb_pretty(payload) FROM observations WHERE domain='air' ORDER BY observed_at DESC LIMIT 1;"
```

---

## 3. Run the detector pipeline

Detectors: `proximity`, `spoofing`, `no_fly_zone`. Each runner is the same image
with a different `--detector`.

**No-fly-zone zones** are committed: 15 real FAA zones in
`air/detectors/no_fly_zone/fixtures/airspace/klyh-local-faa.geojson`, i.e. the
Lynchburg area (within 65 nm of KLYH: Farmville, Evers and Barfoot MOAs, and
Fort Pickett's restricted area R-6602) plus P-56 over Washington, DC. Nothing to
generate. Expect few detections: MOAs are legal to fly through and score LOW/INFO,
and in a one-hour replay of real traffic only Evers South MOA fired.

Refresh them each FAA cycle (8 weeks; needs internet) and commit the result:

```bash
python scripts/make_faa_airspace.py --radius-nm 65 --also "P-56" --out air/detectors/no_fly_zone/fixtures/airspace/klyh-local-faa.geojson
```

### One-shot (recommended for testing)

Run a single read→detect→persist pass and exit. Add `--build` on the first run so
the image reflects current code:

```bash
docker compose --profile runners run --rm --build proximity-runner --detector proximity --once
```

```bash
docker compose --profile runners run --rm spoofing-runner --detector spoofing --once
```

```bash
docker compose --profile runners run --rm no-fly-zone-runner --detector no_fly_zone --once
```

Optional overrides (defaults per detector live in `scripts/run_live_detector.py`):
`--window-s` (lookback seconds), `--step-s`, `--poll-interval-s`. Example — read a
wider 10-minute window:

```bash
docker compose --profile runners run --rm proximity-runner --detector proximity --once --window-s 600
```

### Continuous (run the detectors on a timer)

Start all three runner services in the background; each loops on its own interval:

```bash
docker compose --profile runners up -d --build
```

Follow a runner's logs:

```bash
docker logs --tail 20 -f skywatch-proximity-runner
```

---

## 4. Check detector output

Every run writes a heartbeat to `detector_runs` (status + counts of observations
read and detections written):

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -c "SELECT detector_id, status, counts, started_at FROM detector_runs ORDER BY started_at DESC LIMIT 5;"
```

How many detections each table holds:

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -c "SELECT 'proximity' AS detector, count(*) FROM proximity_detections UNION ALL SELECT 'spoofing', count(*) FROM spoofing_detections UNION ALL SELECT 'no_fly_zone', count(*) FROM no_fly_zone_detections;"
```

What a detection row looks like (proximity):

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -x -c "SELECT detector_id, detection_type, severity, confidence, entity_id, member_entity_ids, predicted_horizontal_nm, predicted_vertical_ft, t_cpa_seconds, temporal_bounds_start FROM proximity_detections ORDER BY last_detected_at DESC LIMIT 1;"
```

What a detection row looks like (no-fly-zone). One row per incursion: it appears
on entry with no end time (still inside the zone) and is updated in place until
the aircraft leaves:

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -x -c "SELECT entity_id, zone_id, zone_name, zone_type, severity, confidence, temporal_bounds_start, temporal_bounds_end, duration_seconds FROM no_fly_zone_detections ORDER BY last_detected_at DESC LIMIT 1;"
```

> A run with `status=SUCCESS` and `detections=0` is normal — it means the detector
> read observations but nothing met its criteria (a "quiet sky"), not a failure.

Open an interactive SQL shell for ad-hoc queries:

```bash
docker exec -it skywatch-db psql -U skywatch -d skywatch
```

---

## 5. Take it down

Stop and remove the containers but **keep the data** (the DB volume persists):

```bash
docker compose --profile poller --profile runners down
```

Stop **and wipe the database** (removes the volume; the schema reloads fresh on
the next `up`). Use this to reset, or after changing anything in `db/schema/`:

```bash
docker compose down -v
```

Stop a single continuous runner without touching the rest:

```bash
docker compose stop proximity-runner
```

---

## Known gotchas

- **Stale schema / "relation does not exist".** The schema in `db/schema/` only
  loads on an *empty* volume. If you add or change a migration, the existing
  volume keeps the old schema — run `docker compose down -v` then `up` to reload,
  or apply the one file by hand:
  `docker exec -i skywatch-db psql -U skywatch -d skywatch < db/schema/00X_xxx.sql`.
- **Rebuild after code changes.** Edits under `air/` or `scripts/` only take
  effect in the containers after `--build`.
- **No-Fly-Zone on test zones?** `docker logs skywatch-no-fly-zone-runner` shows
  `using TEST zones` if the committed zone file is missing from the image.
  Detections with `zone_id` P-901, TFR-6/1234 or LYNCHBURG-MOA are test zones.
- **Zero detections is not always a quiet sky.** The live feed nests the ADS-B
  fields inside the SENTINEL envelope (`payload.payload`, readsb names such as
  `alt_baro`). Until the reader handles that (#121), live observations reach the
  detectors with no altitude, NIC/NACp, squawk or callsign: no-fly-zone skips every
  aircraft and still reports `SUCCESS`. Check:
  `docker exec skywatch-db psql -U skywatch -d skywatch -c "SELECT payload->'payload' ? 'alt_baro' AS nested_alt FROM observations WHERE domain='air' ORDER BY observed_at DESC LIMIT 1;"`
- **Poller not inserting?** Check `docker logs skywatch-adsb-poller`. A
  `ConnectTimeout` means the machine is not on an allowlisted network (see
  `docs/ADSB_POSITIONS_FEED_GUIDE.md`); a TLS error means `sentinel-ca.crt` is
  missing from the repo root. Test from the host first:
  `curl --cacert sentinel-ca.crt -m 15 -s -o /dev/null -w "%{http_code}\n" "https://adsb-ingest.sentinel.xenithsolutions.com/v1/adsb/positions.geojson?lookback_minutes=1&limit=1"` (expect `200`).
