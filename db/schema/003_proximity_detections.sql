-- SkyWatch local-dev schema — 003: proximity detections (Proximity team).
--
-- One row per predicted-proximity finding about a PAIR of aircraft. Shared
-- columns are copied unchanged from docs/live_integration/DETECTION_TABLE_COLUMNS.md
-- so air/live/persistence.py can fill them generically; proximity's own columns
-- are at the bottom and are filled by air/detectors/proximity/live.extra_columns.
--
-- Rows are written by persist() with ON CONFLICT (dedup_key) DO UPDATE, so the
-- same finding re-seen by an overlapping window updates its row in place.
--
-- Loaded on first boot of `docker compose up -d db`. After changing this file:
--   docker compose down -v && docker compose up -d db

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.proximity_detections (
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

    -- Proximity-specific: the pair and the predicted closest approach, so a
    -- dashboard can filter "involving aircraft X" or "closer than 0.5 nm"
    -- without opening raw_detection.
    member_entity_ids        TEXT[] NOT NULL,          -- both aircraft, e.g. {aircraft:a1b2c3, aircraft:d4e5f6}
    predicted_horizontal_nm  DOUBLE PRECISION,         -- horizontal separation at closest approach
    predicted_vertical_ft    DOUBLE PRECISION,         -- vertical separation at closest approach
    t_cpa_seconds            DOUBLE PRECISION,         -- seconds from start_time to closest approach

    CONSTRAINT uq_proximity_detections_dedup_key UNIQUE (dedup_key),
    CONSTRAINT chk_proximity_detections_confidence CHECK (confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT chk_proximity_detections_temporal_order
        CHECK (temporal_bounds_end IS NULL OR temporal_bounds_end >= temporal_bounds_start),
    CONSTRAINT chk_proximity_detections_pair CHECK (cardinality(member_entity_ids) = 2)
);

CREATE INDEX IF NOT EXISTS idx_proximity_detections_entity_time
    ON public.proximity_detections (entity_id, temporal_bounds_start DESC);
CREATE INDEX IF NOT EXISTS idx_proximity_detections_last_detected_at
    ON public.proximity_detections (last_detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_proximity_detections_metadata_gin
    ON public.proximity_detections USING GIN (metadata);
CREATE INDEX IF NOT EXISTS idx_proximity_detections_position_gist
    ON public.proximity_detections USING GIST (position);
-- "Detections involving aircraft X", whichever side of the pair it was on.
CREATE INDEX IF NOT EXISTS idx_proximity_detections_members_gin
    ON public.proximity_detections USING GIN (member_entity_ids);
