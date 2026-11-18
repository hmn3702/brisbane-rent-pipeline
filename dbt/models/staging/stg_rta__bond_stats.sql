-- RTA bond statistics, long format. Light renaming only; one row per
-- geo_level x area x dwelling x quarter x measure.

select
    geo_level,
    area_name,                       -- unique within geo_level, e.g. 'West End (4101)'
    area_label,                      -- display name, e.g. 'West End'
    area_postcode,
    dwelling,                        -- 'Flat 2', 'House 3', 'All dwellings', ...
    dwelling_type,
    bedrooms,
    quarter_end,
    measure,
    value::numeric                   as value,
    source_file,
    loaded_at
from {{ source('raw', 'rta_bond_stats') }}
