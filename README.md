# Brisbane rents: what landlords ask vs what tenants sign

[![ci](https://github.com/hmn3702/brisbane-rent-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/hmn3702/brisbane-rent-pipeline/actions/workflows/ci.yml)

An end-to-end data project on the Brisbane rental market. Python pulls in the data, PostgreSQL stores it,
dbt models and tests it, and a Power BI dashboard (kept as code) shows it.

**The question:** Queensland's Residential Tenancies Authority (RTA) publishes the median rent of tenancies
that were *actually signed*. But it only publishes quarterly, about a month after each quarter ends.
Listing sites show what landlords are *asking* today. How far apart are those two numbers in each suburb,
and do suburbs that ask more lease more slowly?

![Where Queensland rents are rising](docs/img/p1_rising.png)

---

## What I found (real RTA data, Sep quarter 2026)

- **Queensland's median weekly rent for new tenancies is $650, up 8.3% on a year earlier.**
- **Headline suburb medians can mislead.** In Toowong, 618 of the 870 new bonds lodged were for dwellings
  RTA classes as "Other". So the suburb's "All dwellings" median ($559) is *lower* than the median for a
  one-bedroom flat ($600). A large share of tenancies near UQ are probably rooms or student accommodation.
  Comparing a suburb's apartment and house listings against that "All dwellings" median would make asking
  rents look far more inflated than they are. The project compares like with like instead, dwelling type
  by dwelling type, and weights by RTA's mix (see *mix-adjusted gap* below).
- **The cheapest quarter to sign is June; the dearest is March.** For a two-bedroom flat in Queensland,
  signed rents run 2.3% above their trend in the March quarter (t = 6.1 across 14 years) and 2.0% below it
  in the June quarter. That 4.3-point swing is worth about $1,500 a year at today's $665 median.
  For three-bedroom houses the swing is much smaller (about 1.6 points, cheapest again in June).
- **The March premium is shrinking.** For two-bedroom flats it averaged +3.1% in 2012–2019 and +1.5% since 2020.
- **March is the student intake.** New leases jump in the March quarter in Springfield Central (+85% vs trend),
  Sippy Downs (+74%), St Lucia (+73%) and Kelvin Grove (+57%). These are the suburbs around university campuses.
  Part of the March rent premium may therefore be a location-mix effect (more leases signed in dearer inner
  suburbs) rather than every landlord charging more. RTA data alone can't separate the two.

> **Status:** the asking-rent side (Domain listings API) is waiting on API access approval. Until then,
> pages 3–4 of the dashboard run on **synthetic listings**. These are flagged in the data
> (`"_synthetic": true`), and the dashboard shows a DEMO banner. Every RTA figure above is real.

## Architecture

```mermaid
flowchart LR
    A[Domain API<br/>rental listings, daily] -->|ingest_domain.py| R[(PostgreSQL<br/>raw)]
    B[RTA bond statistics<br/>xlsx, quarterly] -->|ingest_rta.py| R
    R --> S[dbt staging]
    S --> I[dbt intermediate<br/>listing lifecycle,<br/>suburb x quarter]
    I --> M[dbt marts<br/>rent gap, league table,<br/>trend, leasing speed,<br/>seasonality]
    M -->|export_marts.py| P[Power BI<br/>PBIP: TMDL + PBIR]
    G[GitHub Actions<br/>daily pipeline] -.schedules.-> A
    G -.-> B
    G -.-> S
```

| Layer | Tools |
|---|---|
| Ingestion | Python (requests, openpyxl), OAuth client credentials, retries, idempotent upserts |
| Storage | PostgreSQL (hosted on Neon's free tier): raw JSONB snapshots, a long-format RTA table (~518k suburb and state rows), and an ingest log |
| Transformation | dbt Core: 3 layers, 10 models, 28 data tests |
| Testing | 12 pytest tests (API mocked, real-workbook checks) and 28 dbt schema and singular tests |
| BI | Power BI Project (TMDL semantic model + PBIR report), generated from `powerbi/build_pbip.py` |
| CI | GitHub Actions on every push: pytest, then the full pipeline (RTA parser → synthetic listings → `dbt build`) on a fresh Postgres, plus the same run through `docker compose` |
| Local run | Docker Compose (Postgres 16 + a Python/dbt image) and a Makefile: `make demo` runs everything |
| Orchestration | One scheduled GitHub Actions workflow, run end to end against a hosted Postgres (Neon): RTA reloaded only when the workbook changes, then Domain snapshot, `dbt build`, mart export and a database-size check |

## Engineering decisions worth a look

**1. Daily snapshots turn a "current listings" API into history.**
Domain's API only returns listings that are live right now. Storing one snapshot per day lets the
`int_domain__listings` model rebuild each listing's lifecycle: first seen, last seen, price cuts, and days on
market. Listings already live on the first snapshot are *left-censored*, because their true start date is
unknown. They are excluded from days-on-market instead of being counted as fast leases.

**2. One parser for a messy 12-sheet workbook, built to fail loudly.**
The RTA workbook has 4 geographies × 3 measures, laid out wide (quarters as columns). `ingest_rta.py`
turns it into a single long table and handles the quirks: a trailing space in one sheet name, `''` vs
`None` for suppressed cells, and suburbs that share a name (`West End (4101)` vs `West End (4810)`). It also
checks the latest quarter against the workbook's own contents page. If RTA changes the layout, the load
stops with an error instead of quietly loading wrong numbers.

**3. As-of join, capped.**
RTA publishes about a month after each quarter ends, so today's asking rents are compared with the latest
RTA quarter available. `rta_quarters_behind` records how stale that comparison is. When RTA suppresses a
small cell, the join is allowed to look back at most 2 quarters (`max_rta_lag_quarters`).

**4. Mix-adjusted gap.**
A suburb's headline gap is the per-dwelling gaps (Flat 1, House 3, …) weighted by RTA's new bonds. It is
not "median of all listings vs median of all bonds", because that compares two different dwelling mixes.

**5. A bug caught by testing the dashboard against SQL.**
I wrote SQL that repeats the logic of each DAX measure and checked the dashboard against it. On the demo data,
Toowong showed 8.5% in dbt but 7.8% in DAX. The cause was the as-of join silently reaching back **6 quarters** whenever RTA
had suppressed a cell. I fixed it with the lookback cap, plus a dbt test
(`assert_mix_adjusted_gap_matches_dax_rule`) that keeps the mart and the Power BI measure on the same rule.

**6. Power BI as code.**
The semantic model (TMDL) and the report (PBIR) are plain text, generated by `powerbi/build_pbip.py` and
validated against Microsoft's published JSON schemas. The dashboard can be diffed, reviewed and rebuilt
like any other code. The measures never add up or average medians: one row in context shows the published
median, and several rows show a weighted average.

**7. Seasonality without fooling yourself.**
`int_rta__seasonal_deviation` compares each quarter with a centred 2×4 moving average, which removes the
trend (the Queensland median rose from $342 to $650 a week since 2012) but keeps the seasonal swing. A quarter only gets a value when the
two quarters either side exist (no gaps bridged), the cell has at least 10 new bonds, and the deviation is
within ±40%. That last rule came from a failing test: 55 rows in towns such as Moranbah (subsidised mining
housing) swung wildly. They are flagged as outliers and excluded, rather than widening the test.
`mart_rta_seasonality` reports the mean deviation per quarter with a t-statistic, and only calls a quarter
significant with 5+ years of data and |t| ≥ 2.

## Dashboard

| | |
|---|---|
| ![Trend vs Queensland](docs/img/p2_trend.png) | ![Asking vs signed (demo data)](docs/img/p3_gap.png) |
| **Trend vs Queensland:** a suburb's signed rent against the QLD median since 2017 | **Asking vs signed:** mix-adjusted gap by suburb and dwelling (synthetic listings for now) |
| ![How fast places lease (demo data)](docs/img/p4_speed.png) | |
| **Leasing speed:** days on market and price cuts (synthetic listings for now) | |

![When to sign a lease](docs/img/p5_season.png)

**When to sign a lease:** signed rent and new leases against trend, by quarter, for Queensland and a chosen suburb, plus the March lease surge by suburb. Real RTA data only.

## Repository layout

```
ingest_domain.py, ingest_rta.py   ingestion jobs
sql/                              raw-layer DDL
dbt/                              staging → intermediate → marts, tests, macros
config/suburbs.csv                tracked suburbs + Domain↔RTA name mapping (also a dbt seed)
scripts/                          pipeline runner, schema setup, mart export, synthetic-data generators
powerbi/                          PBIP project, generator, DAX, Power Query, build notes
tests/                            pytest
Dockerfile, docker-compose.yml    Postgres 16 + Python/dbt runtime
Makefile                          one-command entry points (make help)
.github/workflows/                CI (pytest, dbt, Docker) and the daily hosted pipeline
docs/RUNBOOK.md                   setup and run instructions for every stage
```

## Run it

Only Docker is needed. On synthetic data, with no downloads and no API keys:

```bash
make demo     # Postgres + schemas + RTA parser + synthetic listings + dbt build + CSV export
make test     # pytest, database tests on a separate rent_test database
make docs     # dbt docs and lineage graph on http://localhost:8080
```

On real RTA data: download the bond statistics workbook into `data/raw/rta/rta-bond-statistics.xlsx`,
then `make real`. Domain listings are added too if `DOMAIN_CLIENT_ID` and `DOMAIN_CLIENT_SECRET` are in `.env`.
Then open `powerbi/pbip/RentDashboard.pbip` in Power BI Desktop and click Refresh.

No `make` (e.g. Windows PowerShell)? Each target is one Docker command:

```powershell
docker compose up -d --wait db
docker compose run --rm app bash scripts/pipeline.sh demo
```

The database is on `localhost:5433` (user, password and database are all `rent`).
Running without Docker, and the hosted Neon setup, are in **[docs/RUNBOOK.md](docs/RUNBOOK.md)**.

## Data sources and attribution

- **Residential Tenancies Authority (Qld): median rents and bond statistics.** © State of Queensland,
  licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Raw files are not committed;
  `ingest_rta.py --download` fetches them.
- **Domain Group listings API** (pending access). Only aggregated statistics will be published. Raw
  listings, addresses, photos and agent details are never stored in this repository.

---

Built by **Minh Nghia Ha**, Master of IT (Data Science) student at QUT.
