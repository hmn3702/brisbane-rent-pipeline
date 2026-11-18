-- Deviations beyond +/-40% must be flagged as outliers (is_rent_outlier) and kept out of rent_dev_pct.
select * from {{ ref('int_rta__seasonal_deviation') }}
where abs(rent_dev_pct) > 40
