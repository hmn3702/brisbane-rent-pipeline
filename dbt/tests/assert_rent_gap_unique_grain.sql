-- One row per suburb x quarter x dwelling, including the 'All dwellings' roll-up.
select suburb, quarter_end, dwelling, count(*) as n
from {{ ref('mart_rent_gap_suburb_quarter') }}
group by 1, 2, 3
having count(*) > 1
