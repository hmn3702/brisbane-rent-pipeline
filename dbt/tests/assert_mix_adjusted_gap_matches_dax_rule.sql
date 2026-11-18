-- Recompute the mix-adjusted gap with the Power BI [Gap %] rule (per-dwelling gap_pct weighted by
-- RTA new bonds, rows no staler than the 'All dwellings' row) and fail on any difference > 0.1.
with g as (select * from {{ ref('mart_rent_gap_suburb_quarter') }}),
ref_lag as (
    select suburb, quarter_end, rta_quarters_behind as lag, gap_pct_mix_adjusted
    from g where dwelling = 'All dwellings'
),
recomputed as (
    select g.suburb, g.quarter_end,
           round(sum(g.gap_pct * g.rta_new_bonds) / nullif(sum(g.rta_new_bonds), 0), 1) as expected
    from g
    join ref_lag r using (suburb, quarter_end)
    where g.dwelling <> 'All dwellings' and g.gap_pct is not null and g.rta_quarters_behind <= r.lag
    group by 1, 2
)
select r.suburb, r.quarter_end, r.gap_pct_mix_adjusted, c.expected
from ref_lag r
left join recomputed c using (suburb, quarter_end)
where abs(coalesce(r.gap_pct_mix_adjusted, -999) - coalesce(c.expected, -999)) > 0.1
