-- Detrended deviations should roughly cancel out over a year. If the four quarterly averages for
-- Queensland drift far from zero, the trend filter or the contiguity check is broken.
select dwelling, round(avg(rent_dev_pct), 2) as mean_of_quarters, count(*) as quarters
from {{ ref('mart_rta_seasonality') }}
where geo_level = 'state' and n_years_rent >= 5
group by dwelling
having count(*) = 4 and abs(avg(rent_dev_pct)) > 1.0
