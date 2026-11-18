# Runbook — Brisbane Rent Pipeline

How to set up and run each stage. For what the project is and why, see the [README](../README.md).

## Step 1 — Domain ingest (asking rents, daily)

Daily snapshot of live rental listings for the suburbs in `config/suburbs.csv`
→ raw JSON in `data/raw/domain/snapshot_date=YYYY-MM-DD/` → Postgres `raw.domain_rent_listings`.

## Setup
1. Register at developer.domain.com.au → create a project → add the **Agents & Listings** package →
   create an API client with **Client Credentials** grant and scope `api_listings_read`.
2. `pip install -r requirements.txt`
3. `cp .env.example .env` and fill in keys + `DATABASE_URL` (local Postgres or Supabase).
4. `psql "$DATABASE_URL" -f sql/001_raw_schema.sql`

## Run
    python ingest_domain.py                         # fetch today + load
    python ingest_domain.py --skip-db               # fetch, save JSON only
    python ingest_domain.py --reload-from-raw 2026-11-18   # reload saved JSON, no API calls

Check quickly: `SELECT suburb, count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY weekly_rent)
FROM raw.v_domain_rent_quicklook GROUP BY 1 ORDER BY 3 DESC;`

## Tests
    pytest -q                                        # API is mocked, no key needed
    TEST_DATABASE_URL=postgresql://... pytest -q     # also tests the Postgres load

## Scheduling
`.github/workflows/daily_ingest.yml` runs daily at 06:17 Brisbane. Add the three values from `.env`
as repository secrets. Note: raw JSON written on the runner is discarded — Postgres is the store of record there.

## Step 2 — RTA ingest (signed rents, quarterly)

Source: Queensland Residential Tenancies Authority bond statistics (CC BY 4.0).
Median weekly rent of **new tenancies actually signed**, plus new bonds lodged and bonds held,
by postcode (2012→), suburb (Sep 2017→), LGA and all of QLD, per dwelling type and bedrooms.

    psql "$DATABASE_URL" -f sql/002_rta_schema.sql
    python ingest_rta.py                    # parse data/raw/rta/rta-bond-statistics.xlsx -> raw.rta_bond_stats
    python ingest_rta.py --download         # fetch the latest workbook first
    python ingest_rta.py --skip-db --csv-out data/processed/rta_long.csv

- All 12 sheets -> one long table (~935k rows). Full refresh each load, since RTA may revise history.
- `raw.v_rta_quarterly` pivots the three measures and adds year-on-year rent change
  (RTA advises YoY, not quarter-on-quarter, comparisons).
- Duplicate suburb names keep their postcode (`West End (4101)` vs `West End (4810)`):
  `area_name` is the unique key, `area_label` the clean name.
- `config/suburbs.csv` column `rta_suburb` maps Domain suburb names to RTA names
  (e.g. Domain "Brisbane City" = RTA "Brisbane").
- `.github/workflows/quarterly_rta.yml` reloads on the 20th of Jan/Apr/Jul/Oct.

Example:

    SELECT area_label, dwelling, quarter_end, median_weekly_rent, rent_yoy_pct
    FROM raw.v_rta_quarterly
    WHERE geo_level = 'suburb' AND area_name IN ('Toowong', 'St Lucia', 'West End (4101)')
      AND dwelling = 'Flat 2' AND quarter_end = '2026-09-30';

## Step 3 — dbt transformations

```
raw.domain_rent_listings ─► stg_domain__listing_snapshots ─► int_domain__listings ─┬─► mart_rent_gap_suburb_quarter
raw.rta_bond_stats ───────► stg_rta__bond_stats ──────────► int_rta__suburb_quarterly ┼─► mart_rta_suburb_latest
config/suburbs.csv (seed) ──────────────────────────────────────────────────────────┴─► mart_listing_velocity_suburb_month
```

| Model | Grain | What it answers |
|---|---|---|
| `stg_domain__listing_snapshots` | listing × day | asking rent parsed to $/week (pcm → weekly, ranges averaged, "Contact agent" → null) |
| `int_domain__listings` | listing | first/last seen, days on market, price cuts, RTA dwelling bucket (`House 4` = 4+ beds) |
| `int_rta__suburb_quarterly` | suburb × dwelling × quarter | signed median rent, new bonds, bonds held, YoY |
| `mart_rent_gap_suburb_quarter` | tracked suburb × quarter × dwelling | asking vs signed rent; `gap_pct_mix_adjusted` for suburb headlines |
| `mart_rta_suburb_latest` | QLD suburb × dwelling | latest quarter, 1y / 5y change, QLD rank (map page) |
| `mart_rta_suburb_trend` | QLD suburb × dwelling × quarter | history since 2017 with the QLD median alongside |
| `mart_listing_velocity_suburb_month` | tracked suburb × month × dwelling | median days on market, % with price cut |

Run:

    cd dbt
    cp profiles.yml.example profiles.yml        # reads PGHOST/PGUSER/PGPASSWORD/PGDATABASE
    dbt build --profiles-dir .                  # seed + 8 models + 22 tests
    dbt docs generate --profiles-dir . && dbt docs serve --profiles-dir .   # lineage graph

Notes:
- RTA publishes ~1 month after quarter end, so the current Domain quarter is compared with the latest
  RTA quarter (`rta_quarters_behind`). Filter to `rta_quarters_behind = 0` for like-for-like results.
- Do not headline the raw 'All dwellings' `gap_pct`: Domain's listing mix differs from RTA's bond mix
  (RTA includes rooming accommodation). Use `gap_pct_mix_adjusted`.
- No Domain key yet? `python scripts/generate_fake_domain.py --truncate` fills raw.domain_rent_listings
  with FAKE snapshots so you can build and demo everything. Use a separate database for that.

## Step 4 — Power BI

    python scripts/export_marts.py              # marts -> powerbi/data/*.csv + manifest.json

Then follow [`powerbi/README.md`](../powerbi/README.md): Power Query (`power_query.m`), star-schema model, DAX (`measures.dax`),
four report pages, and a table of expected values to check every measure against.
The mart's mix-adjusted gap and the Power BI `[Gap %]` measure follow the same rule, and a dbt test
(`assert_mix_adjusted_gap_matches_dax_rule`) keeps them in sync.

## Continuous integration

`.github/workflows/ci.yml` runs on every push and pull request, against a throwaway Postgres 16 service:

1. `pytest` (API mocked; the database tests run against the service).
2. `scripts/make_rta_fixture.py` builds a small **synthetic** workbook in the RTA layout. It has every tracked
   suburb, plus the real file's quirks: a trailing space in a sheet name, `''` for suppressed cells, and a
   duplicate suburb name. `ingest_rta.py` loads it, so CI never depends on the RTA website.
3. `generate_fake_domain.py` with fixed dates, so the run is deterministic.
4. `dbt build --fail-fast`: the seed, 8 models and 22 tests.
5. `export_marts.py` as a smoke test.

To reproduce CI locally, run the same commands against any empty Postgres database (see `ci.yml`).

The scheduled `daily_ingest` and `quarterly_rta` workflows first check that the repository secrets
(`DATABASE_URL`, and `DOMAIN_CLIENT_ID` for the daily job) exist. Until they do, the jobs skip with a
notice instead of failing.

## Hosted run (Neon + the scheduled pipeline)

`.github/workflows/pipeline.yml` runs daily at 06:17 Brisbane time, and on demand from the Actions tab
(**Run workflow**). It replaces the earlier separate daily and quarterly jobs.

| Step | What it does |
|---|---|
| Schemas | Applies `sql/001`–`003`. Idempotent, so it is safe to run every day |
| RTA | `ingest_rta.py --download --geo suburb,state --if-changed`: downloads the workbook, and loads it only if its SHA-256 differs from the last load in `raw.ingest_log`. Only the suburb and state levels are kept, because the dbt models use nothing else (~118 MB instead of ~206 MB) |
| Domain | `ingest_domain.py`, only when the `DOMAIN_CLIENT_ID` secret exists |
| dbt | `dbt build` (models + tests) |
| Export | Marts → CSV, uploaded as the `powerbi-data` artifact (kept 30 days) |
| Size check | Writes the database size and recent loads to the run summary, and warns above 800 MB |

**Why Neon:** the free plan gives 1 GB of storage per project and scales to zero when idle. Supabase's free
plan (500 MB, paused after a week of inactivity) is too small: the database is ~175 MB with RTA data alone.

### Set-up (once)

1. Create a free project at neon.tech (Postgres 16, region closest to you: AWS Sydney if offered).
2. Copy the **direct** connection string (not the `-pooler` one). It looks like
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`.
3. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**, name it `DATABASE_URL`,
   and paste the connection string.
4. Optional, once Domain approves API access: add `DOMAIN_CLIENT_ID` and `DOMAIN_CLIENT_SECRET` the same way.
5. **Actions → pipeline → Run workflow.** The first run downloads and loads RTA data (~1–2 minutes).

`scripts/pg_env_from_url.py` turns `DATABASE_URL` into the `PG*` variables that dbt reads, and masks the
password in the logs. Power BI can connect to the same database (Get data → PostgreSQL, using the host and
database from the connection string), or use the CSV artifact.

### Storage budget

Domain snapshots grow every day: about 1–2 MB a day for 15 suburbs, depending on payload size
[an estimate until real responses arrive]. Watch the size line in each run's summary. If it nears the
limit, trim snapshots older than a year, or store only the fields the models use.
