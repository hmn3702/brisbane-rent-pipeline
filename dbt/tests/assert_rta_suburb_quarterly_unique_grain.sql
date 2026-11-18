-- One row per suburb x dwelling x quarter after the pivot.
select area_name, dwelling, quarter_end, count(*) as n
from {{ ref('int_rta__suburb_quarterly') }}
group by 1, 2, 3
having count(*) > 1
