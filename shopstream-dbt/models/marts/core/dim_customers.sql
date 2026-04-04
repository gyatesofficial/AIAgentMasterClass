-- dim_customers.sql
-- Customer dimension: one row per customer, enriched with lifetime order metrics.
-- Materialized as a TABLE — BI tools join to this frequently.

{{
  config(
    materialized = 'table',
    tags = ['core', 'daily']
  )
}}

with customers as (

    select * from {{ ref('stg_customers') }}

),

order_history as (

    select * from {{ ref('int_customer_order_history') }}

),

final as (

    select
        -- PK
        customers.customer_id,

        -- Attributes
        customers.first_name,
        customers.last_name,
        customers.first_name || ' ' || customers.last_name   as full_name,
        customers.email,
        customers.country_code,
        customers.is_active,
        customers.signup_month,
        customers.created_at                                  as customer_since,

        -- Lifetime metrics (coalesce handles never-purchased customers)
        coalesce(oh.total_orders, 0)                         as total_orders,
        coalesce(oh.completed_orders, 0)                     as completed_orders,
        coalesce(oh.returned_orders, 0)                      as returned_orders,
        coalesce(oh.lifetime_value, 0)                       as lifetime_value,
        oh.avg_order_value,
        oh.max_order_value,
        oh.first_order_at,
        oh.most_recent_order_at,
        oh.first_order_date,
        coalesce(oh.customer_lifespan_days, 0)               as customer_lifespan_days,
        coalesce(oh.customer_tier, 'never_purchased')        as customer_tier

    from customers
    left join order_history oh using (customer_id)

)

select * from final
