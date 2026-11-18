-- RTA bond statistics in long format. Full refresh on every load (workbook holds full history).
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.rta_bond_stats (
    geo_level      TEXT     NOT NULL CHECK (geo_level IN ('postcode', 'suburb', 'lga', 'state')),
    area_name      TEXT     NOT NULL,  -- as in workbook, e.g. 'West End (4101)'
    area_label     TEXT     NOT NULL,  -- cleaned, e.g. 'West End'
    area_postcode  TEXT,               -- postcode level, or suburbs disambiguated by postcode
    dwelling       TEXT     NOT NULL,  -- 'Flat 2', 'House 3', 'All dwellings', 'Other'
    dwelling_type  TEXT     NOT NULL,  -- 'Flat' | 'House' | 'Townhouse' | 'All' | 'Other'; state level also has 'General Tenancies', 'Rooming Accommodation'
    bedrooms       SMALLINT,
    quarter_end    DATE     NOT NULL,
    measure        TEXT     NOT NULL CHECK (measure IN ('median_rent', 'new_bonds', 'bonds_held')),
    value          NUMERIC  NOT NULL,
    source_file    TEXT     NOT NULL,
    loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (geo_level, area_name, dwelling, quarter_end, measure)
);

CREATE INDEX IF NOT EXISTS ix_rta_label ON raw.rta_bond_stats (geo_level, area_label);

-- Wide view: one row per area x dwelling x quarter with the three measures side by side,
-- plus year-on-year rent change (RTA advises YoY, not QoQ, comparisons because of seasonality).
CREATE OR REPLACE VIEW raw.v_rta_quarterly AS
WITH wide AS (
    SELECT geo_level, area_name, area_label, area_postcode, dwelling, dwelling_type, bedrooms, quarter_end,
           MAX(value) FILTER (WHERE measure = 'median_rent') AS median_weekly_rent,
           MAX(value) FILTER (WHERE measure = 'new_bonds')   AS new_bonds,
           MAX(value) FILTER (WHERE measure = 'bonds_held')  AS bonds_held
    FROM raw.rta_bond_stats
    GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
)
SELECT w.*,
       prev.median_weekly_rent AS median_weekly_rent_prev_year,
       ROUND(100.0 * (w.median_weekly_rent / NULLIF(prev.median_weekly_rent, 0) - 1), 1) AS rent_yoy_pct
FROM wide w
LEFT JOIN wide prev
       ON prev.geo_level = w.geo_level
      AND prev.area_name = w.area_name
      AND prev.dwelling  = w.dwelling
      AND prev.quarter_end = (w.quarter_end - INTERVAL '1 year')::date;  -- quarter ends never fall on 29 Feb
