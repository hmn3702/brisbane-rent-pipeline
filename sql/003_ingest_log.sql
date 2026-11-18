-- One row per successful load: what was loaded, from which file, and how many rows.
-- Used to skip reloading an unchanged RTA workbook and to see pipeline history at a glance.
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.ingest_log (
    id           BIGSERIAL   PRIMARY KEY,
    source       TEXT        NOT NULL,            -- 'rta' | 'domain'
    loaded_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    rows_loaded  INTEGER     NOT NULL,
    file_sha256  TEXT,                            -- RTA workbook hash (NULL for Domain)
    detail       JSONB                            -- e.g. geo levels loaded, snapshot date, API calls
);

CREATE INDEX IF NOT EXISTS ix_ingest_log_source ON raw.ingest_log (source, loaded_at DESC);
