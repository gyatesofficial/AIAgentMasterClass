{{
    config(
        materialized        = 'incremental',
        schema              = 'marts',
        unique_key          = 'order_id',
        incremental_strategy = 'merge',
        cluster_by          = ['order_date', 'region'],
        tags                = ['marts', 'fact', 'orders'],
        description         = 'Order fact table. One row per order. Incremental merge on order_id. Joined with customer and product dimensions.'
    )
}}

/*
    fct_orders
    ----------
    Grain: one row per ORDER_ID

    Incremental logic:
      - On full refresh: processes all records
      - On incremental runs: processes only orders where order_date is within
        the last {{ var('incremental_lookback_days') }} days, plus any records
        where the status has changed (handles late-arriving updates)

    Sources:
      - {{ ref('stg_orders') }}      – order transactions
      - {{ ref('dim_customers') }}   – customer dimension (for surrogate key)
      - {{ ref('stg_products') }}    – product attributes (if available)

    Columns:
      order_id              Natural key from source system
      order_date            Date of the order
      customer_id           Foreign key to dim_customers.customer_id
      customer_key          Surrogate key → dim_customers.customer_key
      product_id            Product identifier
      amount                Order amount (USD)
      status                Order status (COMPLETED/PENDING/CANCELLED/REFUNDED)
      region                Fulfillment region
      is_completed          Boolean shortcut for status = COMPLETED
      is_refunded           Boolean shortcut for status = REFUNDED
      order_year            Year of order_date (for clustering efficiency)
      order_month           Month of order_date
      order_quarter         Quarter (Q1/Q2/Q3/Q4)
      order_week_of_year    ISO week number
      amount_bucket         Categorical spend bucket (XS/S/M/L/XL)
*/

with

orders as (

    select * from {{ ref('stg_orders') }}

    {% if is_incremental() %}
    -- Incremental filter: only re-process recent orders
    -- The lookback window catches late-arriving status updates
    where order_date >= DATEADD(
        'day',
        -{{ var('incremental_lookback_days', 3) }},
        CURRENT_DATE()
    )
    {% endif %}

),

customers as (

    -- Only bring in the surrogate key and natural key for the join
    select
        customer_id,
        customer_key,
        segment,
        country_code
    from {{ ref('dim_customers') }}

),

final as (

    select
        -- Grain / natural key
        o.order_id,

        -- Dates
        o.order_date,
        YEAR(o.order_date)                                          as order_year,
        MONTH(o.order_date)                                         as order_month,
        QUARTER(o.order_date)                                       as order_quarter,
        WEEKOFYEAR(o.order_date)                                    as order_week_of_year,
        DAYOFWEEK(o.order_date)                                     as order_day_of_week,
        DAYNAME(o.order_date)                                       as order_day_name,
        DATE_TRUNC('week', o.order_date)::DATE                      as order_week_start,

        -- Foreign keys
        o.customer_id,
        c.customer_key,                          -- surrogate key for star schema
        o.product_id,

        -- Customer attributes (denormalized for query performance)
        c.segment                                                    as customer_segment,
        c.country_code,

        -- Measures
        o.amount,
        ROUND(o.amount, 2)                                          as amount_rounded,

        -- Status flags
        o.status,
        o.is_completed,
        o.status = 'REFUNDED'                                       as is_refunded,
        o.status = 'CANCELLED'                                      as is_cancelled,
        o.status = 'PENDING'                                        as is_pending,

        -- Geography
        o.region,

        -- Derived bucket
        CASE
            WHEN o.amount <    50 THEN 'XS'
            WHEN o.amount <   200 THEN 'S'
            WHEN o.amount <   500 THEN 'M'
            WHEN o.amount <  1000 THEN 'L'
            ELSE                       'XL'
        END                                                         as amount_bucket,

        -- Audit
        o._loaded_at,
        CURRENT_TIMESTAMP()::TIMESTAMP_NTZ                          as _dbt_updated_at,
        '{{ invocation_id }}'                                       as _dbt_invocation_id

    from orders o
    left join customers c
        on o.customer_id = c.customer_id

)

select * from final
