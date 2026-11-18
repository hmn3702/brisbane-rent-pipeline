-- Raw layer: one row per listing per daily snapshot. Payload kept untouched (JSONB).
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.domain_rent_listings (
    listing_id       BIGINT      NOT NULL,
    snapshot_date    DATE        NOT NULL,
    search_suburb    TEXT        NOT NULL,   -- suburb we queried (may differ from listing's own suburb)
    search_postcode  TEXT        NOT NULL,
    payload          JSONB       NOT NULL,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (listing_id, snapshot_date)
);

CREATE INDEX IF NOT EXISTS ix_domain_rent_snapshot ON raw.domain_rent_listings (snapshot_date);

-- Quick-look view so you can sanity-check data before dbt exists.
-- Weekly rent is parsed from the free-text displayPrice ("$650 per week", "$2,800 pcm", "Contact agent").
CREATE OR REPLACE VIEW raw.v_domain_rent_quicklook AS
WITH base AS (
    SELECT
        listing_id,
        snapshot_date,
        payload->'propertyDetails'->>'suburb'              AS suburb,
        payload->'propertyDetails'->>'postcode'            AS postcode,
        payload->'propertyDetails'->>'propertyType'        AS property_type,
        (payload->'propertyDetails'->>'bedrooms')::numeric AS bedrooms,
        payload->'priceDetails'->>'displayPrice'           AS display_price,
        (payload->>'dateListed')::timestamptz              AS date_listed,
        REPLACE(SUBSTRING(payload->'priceDetails'->>'displayPrice' FROM '\$\s*([0-9][0-9,]*)'), ',', '')::numeric
                                                           AS price_number
    FROM raw.domain_rent_listings
)
SELECT
    *,
    CASE
        WHEN price_number IS NULL THEN NULL
        WHEN display_price ~* '(month|pcm|p\.c\.m)' THEN ROUND(price_number * 12 / 52, 0)
        ELSE price_number
    END AS weekly_rent
FROM base;
