-- One row per Domain listing across all snapshots: when it was first/last seen,
-- first and latest asking rent, and days on market once it disappears (= leased or withdrawn).

{% set buckets = var('rta_bedroom_buckets') %}

with snaps as (
    select * from {{ ref('stg_domain__listing_snapshots') }}
),

bounds as (
    select min(snapshot_date) as first_snapshot, max(snapshot_date) as latest_snapshot
    from snaps
),

per_listing as (
    select
        listing_id,
        min(snapshot_date)                                                       as first_seen,
        max(snapshot_date)                                                       as last_seen,
        count(*)                                                                 as n_snapshots,
        min(date_listed)                                                         as date_listed,
        (array_agg(suburb        order by snapshot_date desc))[1]                as suburb,
        (array_agg(postcode      order by snapshot_date desc))[1]                as postcode,
        (array_agg(property_type order by snapshot_date desc))[1]                as property_type,
        (array_agg(dwelling_type order by snapshot_date desc))[1]                as dwelling_type,
        (array_agg(bedrooms      order by snapshot_date desc))[1]                as bedrooms,
        (array_agg(weekly_rent_asking order by snapshot_date)
            filter (where weekly_rent_asking is not null))[1]                    as first_asking_rent,
        (array_agg(weekly_rent_asking order by snapshot_date desc)
            filter (where weekly_rent_asking is not null))[1]                    as last_asking_rent,
        count(distinct weekly_rent_asking)                                       as n_price_points
    from snaps
    group by listing_id
)

select
    p.*,
    p.last_seen = b.latest_snapshot                                              as is_active,
    -- listed before tracking started: true start date unknown, so days on market is unreliable
    (p.first_seen = b.first_snapshot
        and (p.date_listed is null or p.date_listed < b.first_snapshot))         as is_left_censored,
    case
        when p.last_seen < b.latest_snapshot
         and not (p.first_seen = b.first_snapshot
                  and (p.date_listed is null or p.date_listed < b.first_snapshot))
        then p.last_seen - least(coalesce(p.date_listed, p.first_seen), p.first_seen)
    end                                                                          as days_on_market,
    p.last_asking_rent < p.first_asking_rent                                     as had_price_cut,
    {{ quarter_end('p.first_seen') }}                                            as first_seen_quarter_end,
    -- map to RTA dwelling categories, clamping bedrooms into RTA's buckets (e.g. a 5-bed house -> 'House 4')
    case p.dwelling_type
    {%- for dtype, rng in buckets.items() %}
        when '{{ dtype }}' then '{{ dtype }} ' || least(greatest(coalesce(p.bedrooms, {{ rng[0] }}), {{ rng[0] }}), {{ rng[1] }})
    {%- endfor %}
    end                                                                          as rta_dwelling
from per_listing p
cross join bounds b
