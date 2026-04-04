{{
    config(
        materialized = 'view',
        schema       = 'staging',
        tags         = ['staging', 'orders'],
        description  = 'Staged orders from the raw ingestion layer. Renames columns to snake_case, casts types, and filters out test/internal rows.'
    )
}}

/*
    stg_orders
    ----------
    Source: {{ source('raw', 'orders') }}
    Grain: one row per order_id (unique)

    Transformations applied:
      - Rename columns to snake_case convention
      - Cast ORDER_DATE to DATE
      - Cast AMOUNT to FLOAT (raw may arrive as VARCHAR from CSV)
      - Trim and upper-case STATUS for consistency
      - Filter out internal test orders (customer_id starting with 'TEST')
      - Coalesce NULL region to 'UNKNOWN'
      - Add a boolean flag for completed orders
      - Add dbt metadata columns (_loaded_at)
*/

with

source as (

    select * from {{ source('raw', 'orders') }}

),

renamed as (

    select
        -- Primary key
        ORDER_ID::VARCHAR                                       as order_id,

        -- Foreign keys
        CUSTOMER_ID::VARCHAR                                    as customer_id,
        PRODUCT_ID::VARCHAR                                     as product_id,

        -- Dates
        TRY_TO_DATE(ORDER_DATE::VARCHAR, 'YYYY-MM-DD')         as order_date,
        TRY_TO_TIMESTAMP_NTZ(CREATED_AT::VARCHAR)              as created_at,

        -- Measures
        TRY_TO_DOUBLE(AMOUNT::VARCHAR)                         as amount,

        -- Dimensions – normalize casing
        UPPER(TRIM(STATUS))                                     as status,
        COALESCE(UPPER(TRIM(REGION)), 'UNKNOWN')                as region,

        -- Derived columns
        UPPER(TRIM(STATUS)) = 'COMPLETED'                      as is_completed,

        -- Audit
        CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ as _loaded_at,
        '{{ invocation_id }}'                                  as _dbt_invocation_id

    from source

),

cleaned as (

    select *
    from renamed
    where
        -- Remove internal test rows
        customer_id not like 'TEST%'
        -- Require a valid order_id
        and order_id is not null
        -- Require a parseable order_date
        and order_date is not null
        -- Require a positive amount
        and amount > 0

)

select * from cleaned
