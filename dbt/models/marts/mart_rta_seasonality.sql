-- When in the year are leases dearer, and where does the student intake drive a March surge?
--
-- Grain: area (QLD suburb, or Queensland as a whole) x dwelling x quarter of year.
-- rent_dev_pct / bonds_dev_pct are averages of detrended deviations across years
-- (see int_rta__seasonal_deviation). rent_t_stat tests whether the average differs from 0:
-- |t| >= 2 with at least 5 years is flagged as significant. The period split shows whether the
-- pattern has changed (state series start 2012, suburb series Sep 2017).

{% set min_years = 5 %}

with d as (
    select * from {{ ref('int_rta__seasonal_deviation') }}
),

agg as (
    select
        geo_level,
        area_name,
        area_label,
        dwelling,
        quarter_of_year,
        count(rent_dev_pct)                                                    as n_years_rent,
        count(bonds_dev_pct)                                                   as n_years_bonds,
        avg(rent_dev_pct)                                                      as rent_dev_pct,
        stddev_samp(rent_dev_pct)                                              as rent_dev_sd,
        avg(case when rent_dev_pct > 0 then 1.0 when rent_dev_pct <= 0 then 0.0 end) as share_years_above_trend,
        avg(bonds_dev_pct)                                                     as bonds_dev_pct,
        avg(new_bonds)                                                         as avg_new_bonds,
        avg(rent_dev_pct) filter (where year <  2020)                          as rent_dev_pct_before_2020,
        avg(rent_dev_pct) filter (where year >= 2020)                          as rent_dev_pct_2020_on
    from d
    group by 1, 2, 3, 4, 5
),

scored as (
    select
        a.*,
        (a.rent_dev_pct / nullif(a.rent_dev_sd / sqrt(nullif(a.n_years_rent, 0)), 0))::numeric as rent_t_stat
    from agg a
)

select
    geo_level,
    area_name,
    area_label,
    dwelling,
    quarter_of_year,
    (array['Mar qtr', 'Jun qtr', 'Sep qtr', 'Dec qtr'])[quarter_of_year]       as quarter_label,
    n_years_rent,
    n_years_bonds,
    round(rent_dev_pct, 2)                                                     as rent_dev_pct,
    round(rent_t_stat, 1)                                                      as rent_t_stat,
    (n_years_rent >= {{ min_years }} and abs(rent_t_stat) >= 2)                as is_rent_significant,
    round(100 * share_years_above_trend, 0)                                    as pct_years_above_trend,
    round(rent_dev_pct_before_2020, 2)                                         as rent_dev_pct_before_2020,
    round(rent_dev_pct_2020_on, 2)                                             as rent_dev_pct_2020_on,
    round(bonds_dev_pct, 1)                                                    as bonds_dev_pct,
    round(avg_new_bonds, 0)                                                    as avg_new_bonds,
    -- rank of the quarter within its area x dwelling: 1 = cheapest time to sign
    case when n_years_rent >= {{ min_years }} then
        rank() over (partition by geo_level, area_name, dwelling
                     order by case when n_years_rent >= {{ min_years }} then rent_dev_pct end asc nulls last)
    end                                                                        as cheapest_rank,
    (t.rta_suburb is not null)                                                 as is_tracked
from scored s
left join {{ ref('suburbs') }} t
       on t.rta_suburb = s.area_name
      and s.geo_level = 'suburb'
