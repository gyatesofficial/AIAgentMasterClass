with source as (

    select * from {{ source('shopstream_raw', 'products') }}

),

renamed as (

    select
        id                                          as product_id,
        trim(name)                                  as product_name,
        lower(trim(category))                       as category,
        sku,
        unit_price_cents::integer                   as unit_price_cents,
        {{ cents_to_dollars('unit_price_cents') }}  as unit_price,
        is_active::boolean                          as is_active,
        created_at::date                            as introduced_on

    from source

)

select * from renamed
