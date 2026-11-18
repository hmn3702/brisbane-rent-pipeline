-- Every suburb in config/suburbs.csv must map to a real RTA suburb name,
-- otherwise the rent-gap mart silently loses it.
select s.suburb, s.rta_suburb
from {{ ref('suburbs') }} s
left join (select distinct area_name from {{ ref('stg_rta__bond_stats') }} where geo_level = 'suburb') r
       on r.area_name = s.rta_suburb
where r.area_name is null
