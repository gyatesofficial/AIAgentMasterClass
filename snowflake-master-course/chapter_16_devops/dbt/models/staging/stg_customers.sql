{{
    config(
        materialized = 'view',
        schema       = 'staging',
        tags         = ['staging', 'customers'],
        description  = 'Staged customers from raw layer. Normalizes PII columns, enforces types, and adds segment ordering.'
    )
}}

/*
    stg_customers
    -------------
    Source: {{ source('raw', 'customers') }}
    Grain: one row per customer_id (unique)

    Transformations applied:
      - Lowercase + trim email addresses
      - Normalize phone to digits-only format (E.164 without country code)
      - Title-case full_name
      - Validate country_code is a 2-letter ISO code
      - Map segment values to a canonical set
      - Add segment_rank (numeric ordering for sort/join purposes)
      - Cast is_active to BOOLEAN
      - Parse created_at as TIMESTAMP_NTZ
*/

with

source as (

    select * from {{ source('raw', 'customers') }}

),

renamed as (

    select
        -- Primary key
        CUSTOMER_ID::VARCHAR                                                as customer_id,

        -- PII – normalize carefully
        LOWER(TRIM(EMAIL))                                                  as email,
        -- Strip non-numeric characters from phone
        REGEXP_REPLACE(PHONE::VARCHAR, '[^0-9]', '')                        as phone_digits,
        INITCAP(TRIM(FULL_NAME::VARCHAR))                                   as full_name,

        -- Geography
        UPPER(TRIM(COUNTRY_CODE::VARCHAR))                                  as country_code,

        -- Segment – canonicalize casing
        INITCAP(LOWER(TRIM(SEGMENT::VARCHAR)))                              as segment,

        -- Derived: numeric rank for segment (used in mart joins)
        CASE UPPER(TRIM(SEGMENT::VARCHAR))
            WHEN 'PLATINUM' THEN 4
            WHEN 'GOLD'     THEN 3
            WHEN 'SILVER'   THEN 2
            WHEN 'BRONZE'   THEN 1
            ELSE                  0
        END                                                                 as segment_rank,

        -- Activity flag
        TRY_TO_BOOLEAN(IS_ACTIVE::VARCHAR)                                  as is_active,

        -- Timestamps
        TRY_TO_TIMESTAMP_NTZ(CREATED_AT::VARCHAR)                          as created_at,

        -- Audit columns
        CONVERT_TIMEZONE('UTC', CURRENT_TIMESTAMP())::TIMESTAMP_NTZ        as _loaded_at,
        '{{ invocation_id }}'                                               as _dbt_invocation_id

    from source

),

validated as (

    select *
    from renamed
    where
        -- Require a customer_id
        customer_id is not null
        -- Require a plausible email
        and email like '%@%'
        -- Require a valid 2-letter country code
        and LENGTH(country_code) = 2
        -- Must belong to a known segment
        and segment in ('Bronze', 'Silver', 'Gold', 'Platinum')

)

select * from validated
