-- Warn if more than 30% of the latest snapshot has no parseable asking rent:
-- usually means Domain changed the displayPrice format or the payload field names.
{{ config(severity='warn') }}
with latest as (
    select * from {{ ref('stg_domain__listing_snapshots') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('stg_domain__listing_snapshots') }})
)
select count(*) as n_listings,
       avg(case when weekly_rent_asking is null then 1.0 else 0 end) as unparsed_share
from latest
having avg(case when weekly_rent_asking is null then 1.0 else 0 end) > 0.30
