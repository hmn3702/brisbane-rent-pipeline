select area_name, dwelling, quarter_end, count(*) as n
from {{ ref('mart_rta_suburb_trend') }}
group by 1, 2, 3
having count(*) > 1
