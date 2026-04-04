{{
    config(
        materialized  = 'table',
        schema        = 'marts',
        tags          = ['marts', 'dimension', 'customers'],
        cluster_by    = ['segment', 'country_code'],
        description   = 'Customer dimension table. One row per active customer. Includes lifetime metrics derived from order history.'
    )
}}

/*
    dim_customers
    -------------
    Type 1 SCD (overwrite on change) – no history tracking in this model.
    Use snapshots/snp_customers.sql for SCD Type 2 if history is required.

    Sources:
      - {{ ref('stg_customers') }}   – normalized customer attributes
      - {{ ref('stg_orders') }}      – used to derive lifetime value metrics

    Columns:
      customer_key         Surrogate key (MD5 of customer_id)
      customer_id          Natural / source key
      email                Lowercase-normalized email
      full_name            Title-cased display name
      phone_digits         Phone (digits only)
      country_code         ISO 2-letter country code
      segment              Customer tier (Bronze/Silver/Gold/Platinum)
      segment_rank         Numeric rank of segment (1–4)
      is_active            Whether customer is currently active
      created_at           Account creation timestamp
      first_order_date     Date of customer's first order
      last_order_date      Date of customer's most recent order
      total_orders         Count of all orders (any status)
      completed_orders     Count of COMPLETED orders only
      lifetime_value       Sum of AMOUNT for COMPLETED orders
      avg_order_value      Average order value across completed orders
      days_since_last      Days elapsed since last order (for churn risk)
      is_churned_proxy     TRUE if no order in last 180 days (heuristic)
*/

with

customers as (

    select * from {{ ref('stg_customers') }}

),

orders as (

    select * from {{ ref('stg_orders') }}

),

order_metrics as (

    select
        customer_id,
        MIN(order_date)                                          as first_order_date,
        MAX(order_date)                                          as last_order_date,
        COUNT(order_id)                                          as total_orders,
        SUM(case when is_completed then 1 else 0 end)           as completed_orders,
        SUM(case when is_completed then amount else 0 end)       as lifetime_value,
        AVG(case when is_completed then amount end)              as avg_order_value,
        DATEDIFF('day', MAX(order_date), CURRENT_DATE())         as days_since_last

    from orders
    group by customer_id

),

final as (

    select
        -- Surrogate key (deterministic hash – joins to fact table)
        MD5(c.customer_id)                                       as customer_key,

        -- Natural key
        c.customer_id,

        -- Customer attributes
        c.email,
        c.full_name,
        c.phone_digits,
        c.country_code,
        c.segment,
        c.segment_rank,
        c.is_active,
        c.created_at,

        -- Order-derived metrics (COALESCE handles customers who never ordered)
        COALESCE(om.first_order_date, NULL)                     as first_order_date,
        COALESCE(om.last_order_date,  NULL)                     as last_order_date,
        COALESCE(om.total_orders,     0)                        as total_orders,
        COALESCE(om.completed_orders, 0)                        as completed_orders,
        COALESCE(om.lifetime_value,   0.0)                      as lifetime_value,
        COALESCE(om.avg_order_value,  0.0)                      as avg_order_value,
        COALESCE(om.days_since_last,  NULL)                     as days_since_last,

        -- Churn proxy: no activity in 180 days
        COALESCE(om.days_since_last > 180, TRUE)                as is_churned_proxy,

        -- Customer tenure in days
        DATEDIFF('day', c.created_at::DATE, CURRENT_DATE())     as tenure_days,

        -- Audit
        CURRENT_TIMESTAMP()::TIMESTAMP_NTZ                      as _dbt_updated_at,
        '{{ invocation_id }}'                                   as _dbt_invocation_id

    from customers c
    left join order_metrics om
        on c.customer_id = om.customer_id

)

select * from final
