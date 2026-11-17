# SkyWatch API

A **read-only** HTTP API over the SkyWatch database. The browser app talks only
to this API; it never touches the database. See `docs/FRONTEND_PLAN.md` for how
it fits the club's web app, and `api/main.py` for the full contract.

## Run it

With the database already up (`docker compose up -d db`):

```bash
docker compose up -d api
```

Or locally against the dockerized DB (needs Python 3.12 + the deps):

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --reload
```

Config comes from the environment:

| Var | Default | Meaning |
|-----|---------|---------|
| `SKYWATCH_DB_DSN` | `postgresql://skywatch:skywatch@localhost:5432/skywatch` | Database DSN. In compose it points at the `db` service. |
| `DB_POOL_MAX_SIZE` | `10` | Max pooled connections. |
| `CORS_ALLOW_ORIGINS` | `*` | Comma-separated allowed origins, or `*`. |

Interactive docs at `http://localhost:8000/docs` once it's running.

## Endpoints

All `GET`, all read-only.

| Path | Returns |
|------|---------|
| `/health` | liveness |
| `/health/db` | DB reachable |
| `/observations.geojson` | newest position per aircraft (GeoJSON points) |
| `/observations/tracks?entity_id=` | one aircraft's recent track (GeoJSON line) |
| `/spoofing-detections` | spoofing rows (team-owned shape) |
| `/proximity-detections` | proximity rows (team-owned shape) |
| `/no-fly-zone-detections` | no-fly-zone rows (team-owned shape) |
| `/detector-runs` | detector heartbeats (is it alive?) |

Query params, units, and property names follow
`xenith-sentinel-platform/frontend/ais_map.html`. Detection endpoints return each
row as stored (`to_jsonb(row)` minus the geometry), so a team can add columns to
its table without changing the API.

## Quick check

```bash
curl -s "http://localhost:8000/health"
curl -s "http://localhost:8000/observations.geojson?lookback_hours=6&limit=5"
```
