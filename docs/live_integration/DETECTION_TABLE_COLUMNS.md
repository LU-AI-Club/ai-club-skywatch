# Detection Table — Shared Column Spec

Each detector team **creates and owns its own detection table** (there is no
pre-built shared table). This doc is the common starting point: the columns every
air detection table should carry so the shared persistence adapter
(`air/live/persistence.py`) can write it and TCE/CAATS can read it the same way
for all three detectors.

**How to use it:** copy the base template below into your team's migration, keep
the shared columns as-is, then **add your own detector-specific columns** for the
facts you want queryable without opening `raw_detection`. The migration file and
table names are fixed by the Tech Lead:

| Team | Migration file | Table |
| --- | --- | --- |
| Spoofing | `db/schema/002_spoofing_detections.sql` | `spoofing_detections` |
| Proximity | `db/schema/003_proximity_detections.sql` | `proximity_detections` |
| No-Fly-Zone | `db/schema/004_no_fly_zone_detections.sql` | `no_fly_zone_detections` |

(These become the real SENTINEL migrations.)

---

## Why these columns

They come straight from the vendored `contracts.Detection` (what each detector
emits) plus the maritime detection tables' conventions:

- Everything a `Detection` carries is preserved losslessly in **`raw_detection`**
  (the full `to_dict()`), so nothing is ever thrown away.
- The flattened top-level columns exist so the API, dashboards, and TCE can
  filter and sort **without parsing JSON** (by entity, time, severity, …).
- **`dedup_key`** is the idempotency key: the runner re-processes overlapping
  windows, and the persistence adapter upserts on `dedup_key` so the same finding
  updates in place instead of duplicating.

## Shared base columns (every detector table)

| Column | Type | Source / meaning |
| --- | --- | --- |
| `detection_id` | `UUID PRIMARY KEY` | `Detection.detection_id` |
| `dedup_key` | `TEXT NOT NULL UNIQUE` | string form of `air.windowing.detection_dedup_key`; **the upsert conflict target** |
| `detector_id` | `TEXT NOT NULL` | e.g. `skywatch.spoofing` |
| `detector_version` | `TEXT NOT NULL` | e.g. `0.1.0` |
| `detection_type` | `TEXT NOT NULL` | detector's type string (free text; no value CHECK — a detector may emit several) |
| `severity` | `TEXT NOT NULL` | `CRITICAL`/`HIGH`/`MEDIUM`/`LOW`/`INFO` |
| `confidence` | `DOUBLE PRECISION NOT NULL` | 0.0–1.0 (deviation certainty, **not** threat) |
| `entity_id` | `TEXT NOT NULL` | primary aircraft, `icao24:<hex>` |
| `entities_involved` | `JSONB NOT NULL DEFAULT '[]'` | all `EntityRef`s |
| `temporal_bounds_start` | `TIMESTAMPTZ NOT NULL` | `Detection.temporal_bounds.start_time` |
| `temporal_bounds_end` | `TIMESTAMPTZ` | end (nullable: open/instantaneous) |
| `latitude` | `DOUBLE PRECISION` | for mapping (nullable) |
| `longitude` | `DOUBLE PRECISION` | for mapping (nullable) |
| `position` | `GEOMETRY(Point,4326)` generated | `ST_MakePoint(longitude, latitude)` — for GIST/map queries |
| `evidence` | `JSONB NOT NULL DEFAULT '[]'` | `Detection.evidence` |
| `geospatial_context` | `JSONB NOT NULL DEFAULT '{}'` | `Detection.geospatial_context` |
| `provenance` | `JSONB NOT NULL DEFAULT '{}'` | lineage (required by the platform) |
| `tags` | `JSONB NOT NULL DEFAULT '[]'` | cross-domain tags |
| `metadata` | `JSONB NOT NULL DEFAULT '{}'` | explanation facts, limitations, etc. |
| `raw_detection` | `JSONB NOT NULL DEFAULT '{}'` | **full `Detection.to_dict()`** (lossless) |
| `detection_run_id` | `UUID` | the run that produced it (nullable; → `detector_runs`) |
| `first_detected_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | first time this `dedup_key` was seen |
| `last_detected_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | most recent run that re-asserted it |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | row insert time |
| `updated_at` | `TIMESTAMPTZ` | set on upsert update |

### Detector-specific columns (you add these)

Add the flattened facts an analyst/dashboard wants for *your* detector, e.g.:
- **spoofing:** usually none beyond the base (the finding is per aircraft; detail
  lives in `evidence`/`metadata`).
- **proximity:** `member_entity_ids TEXT[]` (both aircraft),
  `predicted_horizontal_nm`, `predicted_vertical_ft`, `t_cpa_seconds`.
- **no-fly-zone:** `zone_id`, `zone_name`, `zone_type`, `duration_seconds`.

### Recommended indexes

- `UNIQUE (dedup_key)` — required (the upsert target).
- `(entity_id, temporal_bounds_start DESC)` — "detections for aircraft X".
- `(last_detected_at DESC)` — "most recently active" listing (API default).
- `GIN (metadata)` and `GIST (position)` — JSON filters and spatial/map queries.
- Proximity also wants `GIN (member_entity_ids)` for "involving aircraft X".

## Base template (copy into your migration, then extend)

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.<your_table> (
    detection_id           UUID PRIMARY KEY,
    dedup_key              TEXT NOT NULL,
    detector_id            TEXT NOT NULL,
    detector_version       TEXT NOT NULL,
    detection_type         TEXT NOT NULL,
    severity               TEXT NOT NULL,
    confidence             DOUBLE PRECISION NOT NULL,
    entity_id              TEXT NOT NULL,
    entities_involved      JSONB NOT NULL DEFAULT '[]'::jsonb,
    temporal_bounds_start  TIMESTAMPTZ NOT NULL,
    temporal_bounds_end    TIMESTAMPTZ,
    latitude               DOUBLE PRECISION,
    longitude              DOUBLE PRECISION,
    position GEOMETRY(Point, 4326) GENERATED ALWAYS AS (
        CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL
             THEN ST_SetSRID(ST_MakePoint(longitude, latitude), 4326) END
    ) STORED,
    evidence               JSONB NOT NULL DEFAULT '[]'::jsonb,
    geospatial_context     JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance             JSONB NOT NULL DEFAULT '{}'::jsonb,
    tags                   JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_detection          JSONB NOT NULL DEFAULT '{}'::jsonb,
    detection_run_id       UUID,
    first_detected_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_detected_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at             TIMESTAMPTZ,

    -- >>> add your detector-specific columns here <<<

    CONSTRAINT uq_<your_table>_dedup_key UNIQUE (dedup_key),
    CONSTRAINT chk_<your_table>_confidence CHECK (confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT chk_<your_table>_temporal_order
        CHECK (temporal_bounds_end IS NULL OR temporal_bounds_end >= temporal_bounds_start)
);

CREATE INDEX IF NOT EXISTS idx_<your_table>_entity_time
    ON public.<your_table> (entity_id, temporal_bounds_start DESC);
CREATE INDEX IF NOT EXISTS idx_<your_table>_last_detected_at
    ON public.<your_table> (last_detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_<your_table>_metadata_gin
    ON public.<your_table> USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_<your_table>_position_gist
    ON public.<your_table> USING GIST (position);
```

## Shared `detector_runs` table (one, not per detector)

A single heartbeat table the runner/persistence layer writes (one row per run).
**Owned by the persistence component (B).** All three detectors reference it via
`detection_run_id`.

```sql
CREATE TABLE IF NOT EXISTS public.detector_runs (
    detection_run_id UUID PRIMARY KEY,
    detector_id      TEXT NOT NULL,
    detector_version TEXT NOT NULL,
    window_start     TIMESTAMPTZ,
    window_end       TIMESTAMPTZ,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at     TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'RUNNING',  -- RUNNING | SUCCESS | FAILED
    counts           JSONB NOT NULL DEFAULT '{}'::jsonb,
    error            TEXT
);
CREATE INDEX IF NOT EXISTS idx_detector_runs_detector_started
    ON public.detector_runs (detector_id, started_at DESC);
```

## Rules

- Keep the **shared columns and their names exactly** — the persistence adapter
  fills them generically from `Detection.to_dict()`. Only your extra columns are
  yours to name.
- `raw_detection` is **mandatory and lossless** — never drop a field just because
  you didn't flatten it.
- One file per migration under `db/schema/0NN_*.sql`, applied in numeric order
  (the local `docker-compose.yml` loads them on first boot).
- Confirm your table **name** with the Tech Lead before merging.
