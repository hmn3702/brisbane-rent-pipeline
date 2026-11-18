-- One row per listing per daily snapshot, with the asking rent parsed to $/week
-- and the Domain property type mapped onto RTA dwelling types.

with src as (
    select * from {{ source('raw', 'domain_rent_listings') }}
),

extracted as (
    select
        listing_id,
        snapshot_date,
        search_suburb,
        search_postcode,
        -- Domain returns suburb names in upper case; fall back to the suburb we searched
        initcap(coalesce(nullif(payload -> 'propertyDetails' ->> 'suburb', ''), search_suburb)) as suburb,
        coalesce(nullif(payload -> 'propertyDetails' ->> 'postcode', ''), search_postcode)     as postcode,
        payload -> 'propertyDetails' ->> 'propertyType'                                         as property_type,
        nullif(payload -> 'propertyDetails' ->> 'bedrooms', '')::numeric::int                   as bedrooms,
        nullif(payload -> 'propertyDetails' ->> 'bathrooms', '')::numeric                       as bathrooms,
        nullif(payload -> 'propertyDetails' ->> 'carspaces', '')::numeric::int                  as carspaces,
        nullif(payload -> 'propertyDetails' ->> 'latitude', '')::numeric                        as latitude,
        nullif(payload -> 'propertyDetails' ->> 'longitude', '')::numeric                       as longitude,
        payload -> 'priceDetails' ->> 'displayPrice'                                            as display_price,
        nullif(payload ->> 'dateListed', '')::timestamp::date                                   as date_listed
    from src
),

priced as (
    select
        *,
        -- first and (optional) second dollar amount: "$600 - $650 per week" -> 600, 650
        replace(substring(display_price from '\$\s*([0-9][0-9,]*)'), ',', '')::numeric                 as price_1,
        replace(substring(display_price from '\$\s*[0-9][0-9,]*[^$]*\$\s*([0-9][0-9,]*)'), ',', '')::numeric as price_2,
        display_price ~* '(month|pcm|p\.c\.m)'                                                          as is_monthly
    from extracted
),

weekly as (
    select
        *,
        (coalesce((price_1 + price_2) / 2.0, price_1))
            * case when is_monthly then 12.0 / 52 else 1 end as weekly_rent_raw
    from priced
)

select
    listing_id,
    snapshot_date,
    search_suburb,
    search_postcode,
    suburb,
    postcode,
    property_type,
    case
        when lower(property_type) in ('apartmentunitflat', 'studio', 'flat', 'unit', 'apartment', 'penthouse', 'blockofunits')
            then 'Flat'
        when lower(property_type) in ('townhouse', 'terrace', 'semidetached', 'villa', 'duplex')
            then 'Townhouse'
        when lower(property_type) in ('house', 'acreagesemirural', 'rural', 'farm', 'newhomedesigns')
            then 'House'
        else 'Other'
    end                                                     as dwelling_type,
    bedrooms,
    bathrooms,
    carspaces,
    latitude,
    longitude,
    display_price,
    -- discard obvious non-rents (sale prices, typos) rather than let them skew medians
    case when weekly_rent_raw between 80 and 10000 then round(weekly_rent_raw, 0) end as weekly_rent_asking,
    price_2 is not null                                     as is_price_range,
    date_listed
from weekly
