-- Canary for a misread workbook (shifted column, wrong sheet). Queensland's all-dwellings median has
-- moved between -3.8% and +7.8% a quarter since 2012, COVID included. More than 15% means the
-- parser, not the market.
with s as (
    select quarter_end, value,
           lag(value) over (order by quarter_end) as prev_value
    from {{ ref('stg_rta__bond_stats') }}
    where geo_level = 'state' and dwelling = 'All dwellings' and measure = 'median_rent'
)
select quarter_end, value, prev_value, round(100.0 * (value / prev_value - 1), 1) as qoq_pct
from s
where prev_value is not null
  and abs(value / prev_value - 1) > 0.15
