-- RTA suburb-level stats pivoted: one row per suburb x dwelling x quarter,
-- with year-on-year changes (RTA advises YoY rather than QoQ comparisons).

with s as (
    select * from {{ ref('stg_rta__bond_stats') }}
    where geo_level = 'suburb'
),

wide as (
    select
        area_name,
        area_label,
        area_postcode,
        dwelling,
        dwelling_type,
        bedrooms,
        quarter_end,
        max(value) filter (where measure = 'median_rent') as median_weekly_rent,
        max(value) filter (where measure = 'new_bonds')   as new_bonds,
        max(value) filter (where measure = 'bonds_held')  as bonds_held
    from s
    group by 1, 2, 3, 4, 5, 6, 7
)

select
    w.*,
    py.median_weekly_rent                                                         as median_weekly_rent_prev_year,
    round(100.0 * (w.median_weekly_rent / nullif(py.median_weekly_rent, 0) - 1), 1) as rent_yoy_pct,
    round(100.0 * (w.new_bonds / nullif(py.new_bonds, 0) - 1), 1)                   as new_bonds_yoy_pct
from wide w
left join wide py
       on py.area_name   = w.area_name
      and py.dwelling    = w.dwelling
      and py.quarter_end = (w.quarter_end - interval '1 year')::date
