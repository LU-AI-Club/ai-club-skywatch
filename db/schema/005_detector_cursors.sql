CREATE TABLE IF NOT EXISTS public.detector_cursors (
    detector_id TEXT PRIMARY KEY,
    cursor_at   TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
