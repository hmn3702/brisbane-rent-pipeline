-- Asking rent (Domain, new listings) vs signed rent (RTA, new bonds) per tracked suburb,
-- quarter and RTA dwelling category, plus an 'All dwellings' roll-up.
--
-- RTA publishes ~1 month after each quarter ends, so the current quarter's Domain data is
-- compared with the most recent RTA quarter available (as-of join). rta_quarters_behind
-- says how stale that comparison is; filter to 0 for like-for-like analysis. The lookback is
-- capped at var('max_rta_lag_quarters'): when RTA suppresses a small cell for longer, the row
-- gets no signed rent rather than a years-old one.
--
-- The 'All dwellings' row compares two different mixes (Domain listings vs every RTA bond,
-- incl. rooming accommodation), so it also carries gap_pct_mix_adjusted: the per-dwelling gaps
-- weighted by RTA new bonds, using only dwelling rows that are no staler than the 'All dwellings'
-- row itself. This is the same rule as the Power BI [Gap %] measure. Use it for headlines.

with tracked as (
    select suburb, postcode, rta_suburb from {{ ref('suburbs') }}
),

listings as (
    select l.*, t.rta_suburb, t.suburb as tracked_suburb
    from {{ ref('int_domain__listings') }} l
    join tracked t
      on lower(l.suburb) = lower(t.suburb)
     and l.postcode = t.postcode
    where l.first_asking_rent is not null
      and l.rta_dwelling is not null
),

asking as (
    select
        tracked_suburb,
        rta_suburb,
        first_seen_quarter_end                                            as quarter_end,
        coalesce(rta_dwelling, 'All dwellings')                           as dwelling,
        count(*)                                                          as n_new_listings,
        percentile_cont(0.5) within group (order by first_asking_rent)    as median_asking_rent
    from listings
    group by grouping sets (
        (tracked_suburb, rta_suburb, first_seen_quarter_end, rta_dwelling),
        (tracked_suburb, rta_suburb, first_seen_quarter_end)
    )
),

rta as (
    select area_name, dwelling, quarter_end, median_weekly_rent, new_bonds
    from {{ ref('int_rta__suburb_quarterly') }}
    where median_weekly_rent is not null
      and area_name in (select rta_suburb from tracked)
),

joined as (
select
    a.tracked_suburb                                                      as suburb,
    a.rta_suburb,
    a.quarter_end,
    a.dwelling,
    a.n_new_listings,
    round(a.median_asking_rent::numeric, 0)                               as median_asking_rent,
    r.quarter_end                                                         as rta_quarter_end,
    ((extract(year from a.quarter_end) - extract(year from r.quarter_end)) * 4
      + (extract(quarter from a.quarter_end) - extract(quarter from r.quarter_end)))::int
                                                                          as rta_quarters_behind,
    r.median_weekly_rent                                                  as median_signed_rent,
    r.new_bonds                                                           as rta_new_bonds,
    round(a.median_asking_rent::numeric - r.median_weekly_rent, 0)        as gap_dollars,
    round(100.0 * (a.median_asking_rent::numeric / nullif(r.median_weekly_rent, 0) - 1), 1)
                                                                          as gap_pct,
    (a.n_new_listings < 5 or coalesce(r.new_bonds, 0) < 10)               as is_low_sample
from asking a
left join lateral (
    select *
    from rta
    where rta.area_name = a.rta_suburb
      and rta.dwelling = a.dwelling
      and rta.quarter_end <= a.quarter_end
      and (extract(year from a.quarter_end) * 4 + extract(quarter from a.quarter_end))
        - (extract(year from rta.quarter_end) * 4 + extract(quarter from rta.quarter_end))
          <= {{ var('max_rta_lag_quarters') }}
    order by rta.quarter_end desc
    limit 1
) r on true
),

with_ref_lag as (
    select
        j.*,
        max(case when j.dwelling = 'All dwellings' then j.rta_quarters_behind end)
            over (partition by j.suburb, j.quarter_end)                   as all_dwellings_lag
    from joined j
)

select
    w.suburb, w.rta_suburb, w.quarter_end, w.dwelling, w.n_new_listings, w.median_asking_rent,
    w.rta_quarter_end, w.rta_quarters_behind, w.median_signed_rent, w.rta_new_bonds,
    w.gap_dollars, w.gap_pct, w.is_low_sample,
    case when w.dwelling = 'All dwellings' then
        round(
            sum(w.gap_pct * w.rta_new_bonds) filter (
                where w.dwelling <> 'All dwellings' and w.gap_pct is not null
                  and w.rta_quarters_behind <= w.all_dwellings_lag)
                over (partition by w.suburb, w.quarter_end)
            / nullif(sum(w.rta_new_bonds) filter (
                where w.dwelling <> 'All dwellings' and w.gap_pct is not null
                  and w.rta_quarters_behind <= w.all_dwellings_lag)
                over (partition by w.suburb, w.quarter_end), 0)
        , 1)
    end                                                                   as gap_pct_mix_adjusted
from with_ref_lag w
