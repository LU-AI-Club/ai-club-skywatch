-- SkyWatch local-dev schema — 005: detector_runs (SHARED heartbeat table).
--
-- One table, not one per detector. air/live/persistence.py start_run() inserts a
-- RUNNING row each time a detector starts a run, and finish_run() updates it to
-- SUCCESS or FAILED with its counts. Every detection table's detection_run_id
-- points back here. Spec: docs/live_integration/DETECTION_TABLE_COLUMNS.md
-- ("Shared detector_runs table").
--
-- Why it exists: when the detector runs 24/7 we need to see that it is still
-- running. A detector that has silently stopped looks exactly like a quiet sky.

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
