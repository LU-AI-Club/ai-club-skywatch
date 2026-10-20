-- SkyWatch local-dev schema — 001: canonical observations (SHARED, vendored).
--
-- This is a faithful, trimmed copy of the SENTINEL platform's
-- db/schema/001_postgis_observations.sql. It is the canonical input table every
-- detector reads: the ADS-B loader writes rows here with domain = 'air', and the
-- air detectors consume them. Vendored into the club repo (like contracts/) so
-- students can run a local database WITHOUT access to the company-confidential
-- platform repo.
--
-- Keep this in sync with the platform's 001. Do not hand-edit the shape; if the
-- platform table changes, re-vendor it. The maritime risk_zones table is NOT
-- vendored here: SkyWatch's no-fly-zone detector loads airspace from GeoJSON
-- files, not from a database table.
--
-- Requires the TimescaleDB + PostGIS image pinned in docker-compose.yml
-- (timescale/timescaledb-ha:pg14); both extensions are created below.

CREATE EXTENSION IF NOT EXISTS postgis;
DO $$
BEGIN
    EXECUTE 'CREATE EXTENSION IF NOT EXISTS timescaledb';
EXCEPTION
    WHEN duplicate_object OR unique_violation THEN
        IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
            RAISE;
        END IF;
END $$;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS observations (
    observation_id UUID NOT NULL DEFAULT gen_random_uuid(),
    observed_at TIMESTAMPTZ NOT NULL,
    entity_id TEXT NOT NULL,            -- e.g. 'icao24:a1b2c3' for air, 'mmsi:...' for maritime
    domain TEXT NOT NULL,               -- 'air' for ADS-B rows
    source_id TEXT NOT NULL,            -- 'adsb'
    location GEOGRAPHY(POINT, 4326) NOT NULL,
    h3_index_res7 BIGINT NOT NULL,      -- the loader computes these (h3 lib)
    h3_index_res9 BIGINT NOT NULL,
    sog DOUBLE PRECISION,               -- ground speed, knots  (ADS-B: payload.gs)
    cog DOUBLE PRECISION,               -- course over ground, deg (ADS-B: payload.track)
    heading DOUBLE PRECISION,           -- ADS-B: payload.true_heading
    nav_status SMALLINT,                -- AIS-only; NULL for air
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,  -- full envelope: altitude, callsign,
                                                 -- squawk, nic, nacp live HERE for air
    provenance_id UUID NOT NULL,
    raw_record_ref TEXT,
    ingestion_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (observation_id, observed_at)
);

-- TimescaleDB hypertable on observed_at. Harmless (no-op) if already a hypertable.
SELECT create_hypertable(
    'observations',
    'observed_at',
    if_not_exists => TRUE,
    migrate_data => TRUE
);

CREATE INDEX IF NOT EXISTS idx_observations_location_gist
    ON observations USING GIST (location);

CREATE INDEX IF NOT EXISTS idx_observations_h3_res7
    ON observations (h3_index_res7, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_observations_h3_res9
    ON observations (h3_index_res9, observed_at DESC);

CREATE INDEX IF NOT EXISTS idx_observations_entity_observed_at
    ON observations (entity_id, observed_at DESC);

-- The loader relies on this unique index to ignore replays/retries of the same
-- raw record (envelope event_id lands in raw_record_ref).
CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_source_raw_ref_observed_at_unique
    ON observations (source_id, raw_record_ref, observed_at)
    WHERE raw_record_ref IS NOT NULL;

-- Helpful for air-only queries once air rows coexist with maritime ones locally.
CREATE INDEX IF NOT EXISTS idx_observations_domain_observed_at
    ON observations (domain, observed_at DESC);
