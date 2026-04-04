-- stg_customers.sql
-- Staging model: one row per customer account.
-- Responsibilities:
--   1. Rename/alias columns to our internal naming conventions
--   2. Cast data types explicitly
--   3. Apply simple, stateless business logic (e.g. flag derivations)
--   4. Nothing else — no joins, no aggregations

with source as (

    select * from {{ source('shopstream_raw', 'customers') }}

),

renamed as (

    select
        -- identifiers
        id                                          as customer_id,

        -- customer info
        lower(trim(first_name))                     as first_name,
        lower(trim(last_name))                      as last_name,
        lower(trim(email))                          as email,
        upper(trim(country))                        as country_code,

        -- booleans
        is_active::boolean                          as is_active,

        -- timestamps
        created_at::timestamp                       as created_at,
        updated_at::timestamp                       as updated_at,

        -- derived
        date_trunc('month', created_at)::date       as signup_month

    from source

)

select * from renamed
