with source as (

    select * from {{ source('shopstream_raw', 'order_items') }}

),

renamed as (

    select
        id                                              as order_item_id,
        order_id,
        product_id,
        quantity::integer                               as quantity,
        unit_price_cents::integer                       as unit_price_cents,

        -- Convert to dollars for convenience
        {{ cents_to_dollars('unit_price_cents') }}      as unit_price,

        -- Line total
        quantity * unit_price_cents                     as line_total_cents,
        {{ cents_to_dollars('quantity * unit_price_cents') }} as line_total

    from source

)

select * from renamed
