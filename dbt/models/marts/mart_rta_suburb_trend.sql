-- Quarterly RTA history (Sep 2017 ->) for every QLD suburb x dwelling: line charts and
-- "my suburb vs Queensland" comparisons. Rows without a median rent are kept when bonds exist,
-- so bond-volume charts stay complete.

with q as (
    select * from {{ ref('int_rta__suburb_quarterly') }}
),

qld as (
    select
        quarter_end,
        dwelling,
        max(value) filter (where measure = 'median_rent') as qld_median_weekly_rent
    from {{ ref('stg_rta__bond_stats') }}
    where geo_level = 'state'
    group by 1, 2
)

select
    q.area_name,
    q.area_label                                                   as suburb,
    q.area_postcode,
    {{ location_label('q.area_label', 'q.area_postcode') }}        as location_label,
    q.dwelling,
    q.dwelling_type,
    q.bedrooms,
    q.quarter_end,
    q.median_weekly_rent,
    q.rent_yoy_pct,
    q.new_bonds,
    q.bonds_held,
    s.qld_median_weekly_rent,
    round(100.0 * (q.median_weekly_rent / nullif(s.qld_median_weekly_rent, 0) - 1), 1)
                                                                   as premium_vs_qld_pct,
    (t.rta_suburb is not null)                                     as is_tracked
from q
left join qld s
       on s.quarter_end = q.quarter_end
      and s.dwelling    = q.dwelling
left join {{ ref('suburbs') }} t
       on t.rta_suburb = q.area_name
where q.median_weekly_rent is not null
   or q.new_bonds is not null
