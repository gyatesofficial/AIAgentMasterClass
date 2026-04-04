with source as (

    select * from {{ source('shopstream_raw', 'orders') }}

),

renamed as (

    select
        id                                          as order_id,
        customer_id,
        lower(status)                               as status,
        upper(shipping_address_country)             as shipping_country_code,
        created_at::timestamp                       as order_placed_at,
        updated_at::timestamp                       as order_updated_at,

        -- Derived convenience fields
        date_trunc('day',  created_at)::date        as order_date,
        date_trunc('week', created_at)::date        as order_week,
        date_trunc('month',created_at)::date        as order_month,

        -- Status booleans — easier to aggregate downstream
        (status = 'completed')::boolean             as is_completed,
        (status = 'returned')::boolean              as is_returned,
        (status = 'cancelled')::boolean             as is_cancelled

    from source

)

select * from renamed
