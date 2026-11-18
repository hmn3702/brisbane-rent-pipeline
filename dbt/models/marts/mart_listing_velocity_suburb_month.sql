-- How fast rentals lease in each tracked suburb: listings that came off the market in a month,
-- their median days on market and the share that cut the asking price first.

with tracked as (
    select suburb, postcode, rta_suburb from {{ ref('suburbs') }}
),

closed as (
    select
        l.*,
        t.rta_suburb,
        date_trunc('month', l.last_seen)::date as month_start
    from {{ ref('int_domain__listings') }} l
    join tracked t
      on lower(l.suburb) = lower(t.suburb)
     and l.postcode = t.postcode
    where l.days_on_market is not null
)

select
    suburb,
    rta_suburb,                                                           -- key to RTA / Power BI DimSuburb
    month_start,
    {{ quarter_end('month_start') }}                                      as quarter_end,
    coalesce(rta_dwelling, 'All dwellings')                               as dwelling,
    count(*)                                                              as n_listings_closed,
    percentile_cont(0.5) within group (order by days_on_market)           as median_days_on_market,
    round(100.0 * avg(case when had_price_cut then 1 else 0 end), 1)      as pct_with_price_cut,
    percentile_cont(0.5) within group (order by last_asking_rent)         as median_final_asking_rent
from closed
group by grouping sets (
    (suburb, rta_suburb, month_start, rta_dwelling),
    (suburb, rta_suburb, month_start)
)
