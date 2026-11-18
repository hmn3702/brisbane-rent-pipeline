-- No asking rent may be compared with an RTA figure older than var('max_rta_lag_quarters').
select * from {{ ref('mart_rent_gap_suburb_quarter') }}
where rta_quarters_behind > {{ var('max_rta_lag_quarters') }}
