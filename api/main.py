"""SkyWatch read-only API.

A thin, read-only HTTP layer over the SkyWatch database (the same
``observations`` and ``*_detections`` tables the detectors already write to).
The browser app talks only to this API; it never touches the database.

Design notes (see docs/FRONTEND_PLAN.md):
- Read-only. Every route is GET. No writes, no detector commands.
- Conventions (query params, units, GeoJSON property names, ``position_age_hours``)
  follow ``xenith-sentinel-platform/frontend/ais_map.html`` so a frontend ported
  from that file works against this API with minimal change.
- One endpoint per detector. Each returns the detection rows close to raw
  (``to_jsonb(row)`` minus the geometry), so each team owns the shape of its own
  response and can add columns without changing this file.
- ``observations.payload`` has two shapes: the CSV loader writes flat keys
  (``payload.callsign``), the live Xenith poller writes the SENTINEL envelope
  (``payload.payload.flight`` with raw readsb names). Every payload read below
  COALESCEs both so it works on live and CSV rows alike.

Run it:
    uvicorn api.main:app --reload            # from the repo root
    uvicorn main:app --app-dir api --reload  # equivalent
    docker compose up -d db api              # in a container
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, PoolTimeout

# ---------------------------------------------------------------------------
# Configuration (environment, with dev-friendly defaults matching docker-compose)
# ---------------------------------------------------------------------------
DB_DSN = os.environ.get(
    "SKYWATCH_DB_DSN",
    "postgresql://skywatch:skywatch@localhost:5432/skywatch",
)
DB_POOL_MAX_SIZE = int(os.environ.get("DB_POOL_MAX_SIZE", "10"))
CORS_ALLOW_ORIGINS = os.environ.get("CORS_ALLOW_ORIGINS", "*")

# A hard per-statement ceiling so a slow query can never hang a request worker.
STATEMENT_TIMEOUT_MS = 10_000

# The three detector tables, keyed by the path segment the frontend uses. The
# value is a table name this module controls — never user input — so it is safe
# to interpolate into SQL.
DETECTOR_TABLES = {
    "spoofing": "spoofing_detections",
    "proximity": "proximity_detections",
    "no-fly-zone": "no_fly_zone_detections",
}


# ---------------------------------------------------------------------------
# App + database pool lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one shared async connection pool for the life of the process."""
    app.state.db_pool = AsyncConnectionPool(
        conninfo=DB_DSN,
        min_size=0,
        max_size=DB_POOL_MAX_SIZE,
        open=False,
    )
    # wait=False: the API starts even if the DB is not up yet; the first query
    # that needs a connection waits (and 503s on timeout) rather than crashing
    # startup.
    await app.state.db_pool.open(wait=False)
    try:
        yield
    finally:
        await app.state.db_pool.close()


app = FastAPI(
    title="SkyWatch API",
    description="Read-only API over the SkyWatch observations and detections tables.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["*"]
        if CORS_ALLOW_ORIGINS == "*"
        else [o.strip() for o in CORS_ALLOW_ORIGINS.split(",") if o.strip()]
    ),
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# One query helper, with consistent error -> HTTP mapping
# ---------------------------------------------------------------------------
async def _query(request: Request, sql: str, params: list[Any]) -> list[dict[str, Any]]:
    """Run a read query on the pool and return a list of dict rows.

    Database-down maps to 503, any other database error to 500, so the frontend
    can tell "come back later" from "this query is broken".
    """
    pool: AsyncConnectionPool = request.app.state.db_pool
    try:
        async with pool.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")
                await cur.execute(sql, params)
                return list(await cur.fetchall())
    except (psycopg.OperationalError, PoolTimeout) as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable.") from exc
    except psycopg.Error as exc:
        raise HTTPException(status_code=500, detail="Database query failed.") from exc


def _validate_bbox(min_lat, min_lon, max_lat, max_lon) -> None:
    """Require all four bbox corners together, and min < max."""
    provided = [v for v in (min_lat, min_lon, max_lat, max_lon) if v is not None]
    if not provided:
        return
    if len(provided) != 4:
        raise HTTPException(
            status_code=400,
            detail="Provide all of min_lat, min_lon, max_lat, max_lon, or none.",
        )
    if min_lat > max_lat or min_lon > max_lon:
        raise HTTPException(status_code=400, detail="bbox min must be <= max.")


def _geojson(content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(content),
        media_type="application/geo+json",
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness only — does not touch the database."""
    return {"status": "ok"}


@app.get("/health/db")
async def health_db(request: Request) -> dict[str, str]:
    """Readiness — confirms the database answers."""
    await _query(request, "SELECT 1 AS ok", [])
    return {"status": "ok", "database": "ok"}


# ---------------------------------------------------------------------------
# Aircraft positions — newest fix per aircraft
# ---------------------------------------------------------------------------
@app.get("/observations.geojson")
async def observations_geojson(
    request: Request,
    lookback_hours: float = Query(default=1.0, gt=0, le=168),
    limit: int = Query(default=1000, ge=1, le=5000),
    hex: str | None = Query(default=None, pattern=r"^[0-9a-fA-F]{6}$"),
    callsign: str | None = Query(default=None),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
) -> JSONResponse:
    """Newest ADS-B position per aircraft within the lookback window.

    GeoJSON FeatureCollection of Points. Feature ``id`` is the ICAO hex.
    Properties follow ais_map.html conventions (knots, degrees, ISO timestamp,
    ``position_age_hours``). Both ``payload`` shapes are read via COALESCE.
    """
    _validate_bbox(min_lat, min_lon, max_lat, max_lon)

    # Window + identity filters constrain the per-aircraft "newest row" scan.
    inner_clauses = [
        "domain = 'air'",
        "location IS NOT NULL",
        "observed_at >= now() - make_interval(secs => %s)",
    ]
    params: list[Any] = [lookback_hours * 3600.0]
    if hex:
        inner_clauses.append("entity_id = %s")
        params.append(f"icao24:{hex.lower()}")

    # bbox + callsign are applied AFTER picking the newest row per aircraft, so a
    # match is tested against the current position, not any older one.
    outer_clauses = ["TRUE"]
    if callsign and callsign.strip():
        outer_clauses.append("callsign ILIKE %s")
        params.append(f"%{callsign.strip()}%")
    if min_lat is not None:
        outer_clauses.append("latitude BETWEEN %s AND %s")
        outer_clauses.append("longitude BETWEEN %s AND %s")
        params.extend([min_lat, max_lat, min_lon, max_lon])
    params.append(limit)

    sql = f"""
        WITH latest AS (
            SELECT DISTINCT ON (entity_id)
                substring(entity_id FROM 8) AS icao24,
                COALESCE(
                    NULLIF(btrim(payload->'payload'->>'flight'), ''),
                    NULLIF(btrim(payload->>'callsign'), '')
                ) AS callsign,
                COALESCE(payload->'payload'->>'alt_baro', payload->>'altitude_ft') AS altitude,
                COALESCE(payload->'payload'->>'squawk', payload->>'squawk') AS squawk,
                COALESCE(payload->'payload'->>'category', payload->>'emitter_category') AS category,
                sog, cog, heading,
                observed_at,
                EXTRACT(EPOCH FROM (now() - observed_at)) / 3600.0 AS position_age_hours,
                ST_Y(location::geometry) AS latitude,
                ST_X(location::geometry) AS longitude
            FROM observations
            WHERE {" AND ".join(inner_clauses)}
            ORDER BY entity_id, observed_at DESC
        )
        SELECT * FROM latest
        WHERE {" AND ".join(outer_clauses)}
        ORDER BY observed_at DESC
        LIMIT %s
    """
    rows = await _query(request, sql, params)

    features = [
        {
            "type": "Feature",
            "id": row["icao24"],
            "geometry": {
                "type": "Point",
                "coordinates": [row["longitude"], row["latitude"]],
            },
            "properties": {"source_id": "adsb", **row},
        }
        for row in rows
    ]
    return _geojson({"type": "FeatureCollection", "features": features})


# ---------------------------------------------------------------------------
# One aircraft's recent track
# ---------------------------------------------------------------------------
@app.get("/observations/tracks")
async def observation_track(
    request: Request,
    entity_id: str = Query(..., description="icao24:xxxxxx or a bare 6-hex ICAO."),
    lookback_hours: float = Query(default=6.0, gt=0, le=168),
    limit: int = Query(default=2000, ge=1, le=10000),
) -> JSONResponse:
    """One aircraft's path over the lookback window as a GeoJSON LineString.

    ``properties.points[]`` carries per-fix metadata (time, speed, course,
    heading, altitude) in the same order as the line coordinates.
    """
    normalized = entity_id if ":" in entity_id else f"icao24:{entity_id.lower()}"

    sql = """
        SELECT
            observed_at,
            ST_Y(location::geometry) AS latitude,
            ST_X(location::geometry) AS longitude,
            sog, cog, heading,
            COALESCE(payload->'payload'->>'alt_baro', payload->>'altitude_ft') AS altitude
        FROM observations
        WHERE domain = 'air'
          AND location IS NOT NULL
          AND entity_id = %s
          AND observed_at >= now() - make_interval(secs => %s)
        ORDER BY observed_at ASC
        LIMIT %s
    """
    rows = await _query(request, sql, [normalized, lookback_hours * 3600.0, limit])

    coordinates = [[r["longitude"], r["latitude"]] for r in rows]
    feature = {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coordinates},
        "properties": {
            "entity_id": normalized,
            "point_count": len(rows),
            "start": rows[0]["observed_at"] if rows else None,
            "end": rows[-1]["observed_at"] if rows else None,
            "points": rows,
        },
    }
    return _geojson({"type": "FeatureCollection", "features": [feature]})


# ---------------------------------------------------------------------------
# Detections — one endpoint per detector, team-owned envelope
# ---------------------------------------------------------------------------
async def _detections(
    request: Request,
    table: str,
    severity: str | None,
    entity_id: str | None,
    since_hours: float | None,
    limit: int,
    bbox: tuple[float | None, float | None, float | None, float | None],
    extra: list[tuple[str, Any]] | None = None,
) -> JSONResponse:
    """Shared body for the three detector endpoints.

    Returns the rows as stored (``to_jsonb`` minus the ``position`` geometry),
    so whatever columns a team's table has — shared or detector-specific — flow
    through untouched. ``table`` comes from DETECTOR_TABLES, never user input.

    ``extra`` lets one detector add filters the others have no use for, as
    (sql_fragment, value) pairs. The fragment is written by the endpoint and
    the value is always a parameter, so a caller's input never reaches the SQL
    text. Default None, so the other two endpoints are unchanged.
    """
    min_lat, min_lon, max_lat, max_lon = bbox
    _validate_bbox(min_lat, min_lon, max_lat, max_lon)

    clauses = ["TRUE"]
    params: list[Any] = []
    if severity:
        clauses.append("severity = %s")
        params.append(severity)
    if entity_id:
        clauses.append("entity_id = %s")
        params.append(entity_id)
    if since_hours is not None:
        clauses.append("last_detected_at >= now() - make_interval(secs => %s)")
        params.append(since_hours * 3600.0)
    if min_lat is not None:
        clauses.append("latitude BETWEEN %s AND %s")
        clauses.append("longitude BETWEEN %s AND %s")
        params.extend([min_lat, max_lat, min_lon, max_lon])
    for fragment, value in extra or []:
        clauses.append(fragment)
        params.append(value)
    params.append(limit)

    sql = f"""
        SELECT to_jsonb(d) - 'position' AS row
        FROM {table} AS d
        WHERE {" AND ".join(clauses)}
        ORDER BY last_detected_at DESC
        LIMIT %s
    """
    rows = await _query(request, sql, params)
    return JSONResponse(content=jsonable_encoder([r["row"] for r in rows]))


# The rules the spoofing detector can fire, as written into metadata.gate.
# Listed rather than accepted free-form so an unknown value is a 422 the caller
# can see, not an empty result they have to guess at.
SPOOFING_GATES = (
    "speed_delta_v1",
    "turn_rate_v1",
    "vrate_delta_v1",
    "nic_floor_v1",
    "identity_drift_v1",
    "teleport_v1",
    "subterrain_v1",
    "coexistence_v1",
    "pingpong_v1",
    "reappear_v1",
    "registry_mismatch_v1",
)


@app.get("/spoofing-detections")
async def spoofing_detections(
    request: Request,
    severity: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    since_hours: float | None = Query(default=None, gt=0, le=720),
    limit: int = Query(default=500, ge=1, le=5000),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
    gate: str | None = Query(
        default=None,
        description="Only findings from this rule, e.g. speed_delta_v1.",
    ),
    min_confidence: float | None = Query(
        default=None, ge=0.0, le=1.0,
        description="Only findings at or above this confidence.",
    ),
) -> JSONResponse:
    """Spoofing findings, with two filters the shared endpoint cannot provide.

    The spoofing table has no detector-specific columns on purpose: a finding
    is about one aircraft, and what varies between rules -- which gate fired,
    the measured value against its threshold -- lives in ``metadata``. That
    keeps the table stable when a rule is added, but it means "show me only the
    speed anomalies" cannot be expressed through ``severity`` or ``entity_id``.

    ``gate`` reaches into ``metadata`` to do it, using the GIN index the
    migration created for exactly this. ``min_confidence`` is here because
    severity is a coarse bucket and confidence is the continuous number behind
    it; "LOW but 0.9 confident" is a different question from "LOW".

    Both are additive. The rows come back in the same shape as every other
    detector's, so nothing that already reads this endpoint has to change.
    """
    if gate is not None and gate not in SPOOFING_GATES:
        raise HTTPException(
            status_code=422,
            detail=f"unknown gate {gate!r}; expected one of {list(SPOOFING_GATES)}",
        )

    extra: list[tuple[str, Any]] = []
    if gate is not None:
        # Parameterised, and matched against the tuple above, so nothing from
        # the caller is ever interpolated into SQL.
        extra.append(("metadata->>'gate' = %s", gate))
    if min_confidence is not None:
        extra.append(("confidence >= %s", min_confidence))

    return await _detections(
        request, DETECTOR_TABLES["spoofing"], severity, entity_id, since_hours,
        limit, (min_lat, min_lon, max_lat, max_lon), extra=extra,
    )


@app.get("/spoofing-gates")
async def spoofing_gates(
    request: Request,
    since_hours: float = Query(default=24.0, gt=0, le=720),
) -> JSONResponse:
    """How many findings each rule produced, newest window first.

    A page can compute this from the detection list, but only for the rows it
    already fetched -- which the ``limit`` caps. Counting in the database is
    both honest and cheaper, and it lets the dashboard show "0" for a rule that
    is live but quiet, which an empty list cannot distinguish from a rule that
    does not exist.
    """
    sql = """
        SELECT metadata->>'gate' AS gate,
               count(*)          AS count,
               max(last_detected_at) AS latest,
               avg(confidence)   AS avg_confidence
        FROM spoofing_detections
        WHERE last_detected_at >= now() - make_interval(secs => %s)
          AND metadata->>'gate' IS NOT NULL
        GROUP BY 1
        ORDER BY 2 DESC
    """
    rows = await _query(request, sql, [since_hours * 3600.0])
    seen = {r["gate"]: r for r in rows}
    out = [
        {
            "gate": g,
            "count": int(seen[g]["count"]) if g in seen else 0,
            "latest": seen[g]["latest"] if g in seen else None,
            "avg_confidence": (
                float(seen[g]["avg_confidence"]) if g in seen and seen[g]["avg_confidence"] is not None else None
            ),
        }
        for g in SPOOFING_GATES
    ]
    return JSONResponse(content=jsonable_encoder(out))


@app.get("/proximity-detections")
async def proximity_detections(
    request: Request,
    severity: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    since_hours: float | None = Query(default=None, gt=0, le=720),
    limit: int = Query(default=500, ge=1, le=5000),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
) -> JSONResponse:
    return await _detections(
        request, DETECTOR_TABLES["proximity"], severity, entity_id, since_hours,
        limit, (min_lat, min_lon, max_lat, max_lon),
    )


@app.get("/no-fly-zone-detections")
async def no_fly_zone_detections(
    request: Request,
    severity: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    since_hours: float | None = Query(default=None, gt=0, le=720),
    limit: int = Query(default=500, ge=1, le=5000),
    min_lat: float | None = Query(default=None, ge=-90, le=90),
    min_lon: float | None = Query(default=None, ge=-180, le=180),
    max_lat: float | None = Query(default=None, ge=-90, le=90),
    max_lon: float | None = Query(default=None, ge=-180, le=180),
) -> JSONResponse:
    return await _detections(
        request, DETECTOR_TABLES["no-fly-zone"], severity, entity_id, since_hours,
        limit, (min_lat, min_lon, max_lat, max_lon),
    )


# ---------------------------------------------------------------------------
# Detector liveness — a quiet sky and a dead detector look identical otherwise
# ---------------------------------------------------------------------------
@app.get("/detector-runs")
async def detector_runs(
    request: Request,
    detector_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> JSONResponse:
    """Recent detector-run heartbeats (status, counts, timings), newest first."""
    clauses = ["TRUE"]
    params: list[Any] = []
    if detector_id:
        clauses.append("detector_id = %s")
        params.append(detector_id)
    params.append(limit)

    sql = f"""
        SELECT detection_run_id, detector_id, detector_version,
               window_start, window_end, started_at, completed_at,
               status, counts, error
        FROM detector_runs
        WHERE {" AND ".join(clauses)}
        ORDER BY started_at DESC
        LIMIT %s
    """
    rows = await _query(request, sql, params)
    return JSONResponse(content=jsonable_encoder(rows))
