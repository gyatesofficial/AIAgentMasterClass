-- fct_orders.sql
-- Order fact table: one row per order, grain = order_id.
-- The "spine" of most revenue and operations analysis.

{{
  config(
    materialized = 'table',
    tags = ['core', 'daily']
  )
}}

with orders as (

    select * from {{ ref('int_orders_with_payments') }}

),

customers as (

    select
        customer_id,
        customer_tier,
        signup_month,
        country_code

    from {{ ref('dim_customers') }}

),

order_items_agg as (

    select
        order_id,
        count(distinct product_id)  as distinct_product_count,
        sum(quantity)               as total_items,
        sum(line_total_cents)       as items_total_cents,
        sum(line_total)             as items_total

    from {{ ref('stg_order_items') }}
    group by 1

),

final as (

    select
        -- Grain: one row per order
        orders.order_id,
        orders.customer_id,

        -- Order attributes
        orders.status,
        orders.order_date,
        orders.order_week,
        orders.order_month,
        orders.order_placed_at,
        orders.order_updated_at,
        orders.shipping_country_code,

        -- Payment attributes
        orders.payment_method,
        orders.paid_at,
        orders.has_successful_payment,
        orders.failed_payment_count,
        orders.refund_count,

        -- Revenue
        orders.order_amount                             as revenue,
        orders.order_amount_cents                       as revenue_cents,
        oi.items_total,
        oi.items_total_cents,
        oi.distinct_product_count,
        oi.total_items,

        -- Status booleans
        orders.is_completed,
        orders.is_returned,
        orders.is_cancelled,

        -- Customer context (denormalized for BI convenience)
        customers.customer_tier                         as customer_tier_at_order,
        customers.signup_month                          as customer_signup_month,
        customers.country_code                          as customer_country_code

    from orders
    left join customers      using (customer_id)
    left join order_items_agg oi using (order_id)

)

select * from final
