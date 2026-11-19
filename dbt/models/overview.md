{% docs __overview__ %}
# Brisbane rent pipeline: data model

This site documents the dbt project behind the
[Queensland rents dashboard](https://hmn3702.github.io/brisbane-rent-pipeline/).
It turns two raw sources into tested tables for the dashboard and for Power BI.
Code, method and decisions are on [GitHub](https://github.com/hmn3702/brisbane-rent-pipeline).

## Sources (`raw` schema)

| Table | What it is |
|---|---|
| `raw.rta_bond_stats` | Queensland Residential Tenancies Authority bond statistics: median rent, new bonds and active bonds per suburb (and state), dwelling type and quarter. One row per area, dwelling, quarter and measure. Signed rents, CC BY 4.0. |
| `raw.domain_rent_listings` | Daily snapshots of Domain rental listings (asking rents). Built and tested, but **empty in this deployment** until Domain API access is approved. |

## Layers

1. **staging** (`stg_*`, views): rename, type and clean each source. One model per source, no joins.
2. **intermediate** (`int_*`, tables): reshape for analysis. `int_rta__suburb_quarterly` puts one quarter
   of one suburb and dwelling type on a row. `int_rta__seasonal_deviation` compares each quarter's rent with
   a centred four-quarter moving average. `int_domain__listings` collapses daily snapshots into one row per listing.
3. **marts** (`mart_*`, tables): what the dashboard reads.
   - `mart_rta_suburb_latest`: latest quarter per suburb and dwelling, with 1- and 5-year change and Queensland rank.
   - `mart_rta_suburb_trend`: every quarter per suburb and dwelling, with the Queensland median alongside.
   - `mart_rta_seasonality`: average deviation from trend for each quarter of the year, with a t-statistic.
   - `mart_rent_gap_suburb_quarter` and `mart_listing_velocity_suburb_month`: asking vs signed rent and
     leasing speed (wait for Domain data).

The seed `suburbs` (from `config/suburbs.csv`) lists the tracked suburbs and maps Domain suburb names to RTA names.

## How to read the lineage graph

Click the round button at the bottom right. Data flows left to right: green nodes are the raw sources, then
staging, intermediate and marts. To hide the tests, type `test_type:singular` in the **--exclude** box and
click **Update Graph**. Click any model in the left panel for its columns, tests and compiled SQL.

## Data quality

39 tests run on every build: uniqueness of each table's grain, not-null keys, accepted values, and range
and volume checks whose thresholds come from the real data (for example, Queensland's median rent has never
moved more than 7.8% in a quarter, so a move above 15% fails as a parsing error).

The scheduled pipeline uses **write-audit-publish**: every layer is built into `*__audit` schemas, all tests
run there, and only if every test passes are the audit schemas swapped in, in one transaction. Readers never
see a partly built or untested table.
{% enddocs %}
