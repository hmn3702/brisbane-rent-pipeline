-- Seasonal deviation of signed rents and new bonds from their trend, per area x dwelling x quarter.
--
-- Trend = centred 2x4 moving average (the standard quarterly trend filter): weights
-- 1/8, 1/4, 1/4, 1/4, 1/8 on t-2 .. t+2. Deviation = value / trend - 1. Rents rise ~6% a
-- year, so comparing raw quarters would just measure growth; detrending isolates seasonality.
--
-- A deviation is only computed when all five quarters exist and are contiguous (suppressed
-- RTA cells leave gaps, and a gap would silently stretch the window).

{% set min_bonds = 10 %}
{% set max_abs_dev = 40 %}   {# beyond this it is a data quirk (e.g. subsidised mining-town housing), not seasonality #}

with s as (
    select
        geo_level,
        area_name,
        area_label,
        dwelling,
        quarter_end,
        extract(year from quarter_end)::int                                      as year,
        extract(quarter from quarter_end)::int                                   as quarter_of_year,
        (extract(year from quarter_end) * 4 + extract(quarter from quarter_end))::int as q_index,
        max(value) filter (where measure = 'median_rent')                        as rent,
        max(value) filter (where measure = 'new_bonds')                          as new_bonds
    from {{ ref('stg_rta__bond_stats') }}
    where geo_level in ('suburb', 'state')
    group by 1, 2, 3, 4, 5
),

windowed as (
    select
        s.*,
        lag(q_index, 2)  over w as q_m2,
        lead(q_index, 2) over w as q_p2,
        (0.5 * lag(rent, 2) over w + lag(rent, 1) over w + rent
           + lead(rent, 1) over w + 0.5 * lead(rent, 2) over w) / 4             as rent_trend,
        (0.5 * lag(new_bonds, 2) over w + lag(new_bonds, 1) over w + new_bonds
           + lead(new_bonds, 1) over w + 0.5 * lead(new_bonds, 2) over w) / 4   as bonds_trend
    from s
    window w as (partition by geo_level, area_name, dwelling order by quarter_end)
)

select
    geo_level,
    area_name,
    area_label,
    dwelling,
    quarter_end,
    year,
    quarter_of_year,
    rent,
    round(rent_trend, 2)                                                   as rent_trend,
    -- rent medians from very few new bonds jump around, and a few series swing wildly
    -- (Moranbah flats: $100 one quarter, $580 the next). Both are kept out of the averages.
    case when new_bonds >= {{ min_bonds }}
          and abs(rent / nullif(rent_trend, 0) - 1) <= {{ max_abs_dev }} / 100.0
         then round(100 * (rent / nullif(rent_trend, 0) - 1), 3) end       as rent_dev_pct,
    (new_bonds >= {{ min_bonds }}
       and abs(rent / nullif(rent_trend, 0) - 1) > {{ max_abs_dev }} / 100.0)  as is_rent_outlier,
    new_bonds,
    round(bonds_trend, 2)                                                  as bonds_trend,
    round(100 * (new_bonds / nullif(bonds_trend, 0) - 1), 3)               as bonds_dev_pct
from windowed
where q_m2 = q_index - 2
  and q_p2 = q_index + 2
  and (rent_trend is not null or bonds_trend is not null)
