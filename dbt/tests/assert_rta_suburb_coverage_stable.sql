-- Volume check: the latest quarter must report rents for at least 90% as many suburbs as the
-- quarter before (real data: 651 vs 659). A truncated or partial workbook fails here.
with by_q as (
    select quarter_end, count(distinct area_name) as n_suburbs
    from {{ ref('stg_rta__bond_stats') }}
    where geo_level = 'suburb' and measure = 'median_rent'
    group by 1
), last_two as (
    select quarter_end, n_suburbs,
           lag(n_suburbs) over (order by quarter_end) as prev_n,
           row_number() over (order by quarter_end desc) as rn
    from by_q
)
select quarter_end, n_suburbs, prev_n
from last_two
where rn = 1 and prev_n is not null and n_suburbs < 0.9 * prev_n
