-- SkyWatch local-dev schema — 002: spoofing detections.
--
-- Where `skywatch.spoofing` output lands. Built from the shared base template
-- in docs/live_integration/DETECTION_TABLE_COLUMNS.md; the shared columns are
-- kept exactly as specified, because air/live/persistence.py fills them
-- generically from Detection.to_dict() for all three detectors.
--
-- No detector-specific columns. A spoofing finding is about one aircraft, and
-- the detail that varies between rules -- which gate fired, the measured value
-- against its threshold, the feature records behind it -- is already inside
-- `evidence` and `metadata`. Flattening those into columns would mean a new
-- migration every time a rule is added, which is exactly the coupling the
-- shared shape exists to avoid.
--
-- `raw_detection` holds the whole Detection, losslessly. The flattened columns
-- above it exist so the API, the map and TCE can filter and sort without
-- parsing JSON -- never because the JSON is incomplete.
--
-- Upserted on `dedup_key`: the runner re-reads an overlapping window every
-- tick, so the same finding arrives repeatedly and must update in place rather
-- than pile up. 001 creates the postgis and pgcrypto extensions.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.spoofing_detections (
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

    CONSTRAINT uq_spoofing_detections_dedup_key UNIQUE (dedup_key),
    CONSTRAINT chk_spoofing_detections_confidence
        CHECK (confidence BETWEEN 0.0 AND 1.0),
    CONSTRAINT chk_spoofing_detections_temporal_order
        CHECK (temporal_bounds_end IS NULL
               OR temporal_bounds_end >= temporal_bounds_start)
);

-- "Detections for aircraft X", newest first.
CREATE INDEX IF NOT EXISTS idx_spoofing_detections_entity_time
    ON public.spoofing_detections (entity_id, temporal_bounds_start DESC);

-- "What is active now" — the API's default listing.
CREATE INDEX IF NOT EXISTS idx_spoofing_detections_last_detected_at
    ON public.spoofing_detections (last_detected_at DESC);

-- Filtering by gate, score or any other metadata key without a migration.
CREATE INDEX IF NOT EXISTS idx_spoofing_detections_metadata_gin
    ON public.spoofing_detections USING GIN (metadata);

-- Map queries: what fired inside this bounding box.
CREATE INDEX IF NOT EXISTS idx_spoofing_detections_position_gist
    ON public.spoofing_detections USING GIST (position);
