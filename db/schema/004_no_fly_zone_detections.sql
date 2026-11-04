-- SkyWatch local-dev schema — 004: no-fly-zone detections.
--
-- One row per restricted-airspace incursion EPISODE emitted by
-- skywatch.no_fly_zone (air/detectors/no_fly_zone). The persistence layer
-- upserts on dedup_key (string form of air.windowing.detection_dedup_key), so a
-- re-run that re-asserts an episode bumps last_detected_at / updated_at instead
-- of inserting a duplicate.
--
-- Shared columns are identical to every other detector table (spoofing,
-- proximity); only the block marked "no-fly-zone specific" differs.
--
-- detection_run_id points at public.detector_runs, which is owned by the
-- persistence component (B) and is NOT created here. There is deliberately no
-- FK so this script can run before / without that table.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.no_fly_zone_detections (
    -- ---- shared detection columns -------------------------------------------
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

    -- ---- no-fly-zone specific -----------------------------------------------
    -- Airspace feature id from the GeoJSON fixture, e.g. 'P-56A', 'TFR-6/1234'.
    zone_id                TEXT NOT NULL,
    -- Human-readable name; nullable because some SUA/TFR features have none.
    zone_name              TEXT,
    -- Mirrors air/detectors/no_fly_zone/types.py::ZoneType.
    zone_type              TEXT NOT NULL,
    -- Episode length in seconds, derived from the bounds so it can never
    -- disagree with them. NULL while the episode is open (no end time).
    -- 0 for a single-report episode (start = end).
    duration_seconds DOUBLE PRECISION GENERATED ALWAYS AS (
        EXTRACT(EPOCH FROM (temporal_bounds_end - temporal_bounds_start))::double precision
    ) STORED,

    CONSTRAINT uq_no_fly_zone_detections_dedup_key UNIQUE (dedup_key),
    CONSTRAINT chk_no_fly_zone_detections_confidence
        CHECK (confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT chk_no_fly_zone_detections_temporal_order
        CHECK (temporal_bounds_end IS NULL OR temporal_bounds_end >= temporal_bounds_start),
    CONSTRAINT chk_no_fly_zone_detections_zone_type
        CHECK (zone_type IN ('PROHIBITED', 'RESTRICTED', 'TFR', 'WARNING', 'ALERT', 'MOA'))
);

-- "detections for aircraft X"
CREATE INDEX IF NOT EXISTS idx_no_fly_zone_detections_entity_time
    ON public.no_fly_zone_detections (entity_id, temporal_bounds_start DESC);

-- "most recently active" listing (API default)
CREATE INDEX IF NOT EXISTS idx_no_fly_zone_detections_last_detected_at
    ON public.no_fly_zone_detections (last_detected_at DESC);

-- JSON filters
CREATE INDEX IF NOT EXISTS idx_no_fly_zone_detections_metadata_gin
    ON public.no_fly_zone_detections USING GIN (metadata);

-- spatial / map queries
CREATE INDEX IF NOT EXISTS idx_no_fly_zone_detections_position_gist
    ON public.no_fly_zone_detections USING GIST (position);

-- "incursions into zone Z", newest first
CREATE INDEX IF NOT EXISTS idx_no_fly_zone_detections_zone_time
    ON public.no_fly_zone_detections (zone_id, temporal_bounds_start DESC);
