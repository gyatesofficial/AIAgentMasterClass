with source as (

    select * from {{ source('shopstream_raw', 'payments') }}

),

renamed as (

    select
        id                                          as payment_id,
        order_id,
        lower(payment_method)                       as payment_method,
        amount_cents::integer                       as amount_cents,
        {{ cents_to_dollars('amount_cents') }}      as amount,
        lower(status)                               as payment_status,
        created_at::timestamp                       as paid_at,

        -- Status booleans
        (status = 'success')::boolean               as is_successful,
        (status = 'refunded')::boolean              as is_refunded,
        (status = 'failed')::boolean                as is_failed

    from source

)

select * from renamed
