-- Latest RTA quarter for every Queensland suburb x dwelling: signed median rent,
-- 1-year and 5-year change, and rank among QLD suburbs. Feeds the map / league-table page.

with q as (
    select * from {{ ref('int_rta__suburb_quarterly') }}
),

latest_quarter as (
    select max(quarter_end) as quarter_end from q where median_weekly_rent is not null
),

cur as (
    select q.*
    from q
    join latest_quarter lq using (quarter_end)
    where q.median_weekly_rent is not null
),

five_years_ago as (
    select area_name, dwelling, median_weekly_rent as median_weekly_rent_5y_ago
    from q
    where quarter_end = (select (quarter_end - interval '5 years')::date from latest_quarter)
)

select
    c.area_name,
    c.area_label                                                       as suburb,
    c.area_postcode,
    {{ location_label('c.area_label', 'c.area_postcode') }}           as location_label,
    c.dwelling,
    c.quarter_end,
    c.median_weekly_rent,
    c.median_weekly_rent_prev_year,
    c.rent_yoy_pct,
    f.median_weekly_rent_5y_ago,
    round(100.0 * (c.median_weekly_rent / nullif(f.median_weekly_rent_5y_ago, 0) - 1), 1) as rent_5y_pct,
    c.new_bonds,
    c.bonds_held,
    rank() over (partition by c.dwelling order by c.median_weekly_rent desc)            as rent_rank_qld,
    count(*) over (partition by c.dwelling)                                              as n_suburbs_ranked,
    (t.rta_suburb is not null)                                                           as is_tracked
from cur c
left join five_years_ago f
       on f.area_name = c.area_name
      and f.dwelling  = c.dwelling
left join {{ ref('suburbs') }} t
       on t.rta_suburb = c.area_name
