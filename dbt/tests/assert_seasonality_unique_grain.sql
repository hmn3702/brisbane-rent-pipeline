select geo_level, area_name, dwelling, quarter_of_year, count(*) as n
from {{ ref('mart_rta_seasonality') }}
group by 1, 2, 3, 4
having count(*) > 1
