-- int_customer_order_history.sql
-- Aggregates a customer's full order history into a single row per customer.
-- Used by both dim_customers (for lifetime metrics) and fct_orders (for cohort lookups).

with orders as (

    select * from {{ ref('int_orders_with_payments') }}

),

customer_orders as (

    select
        customer_id,

        count(*)                                            as total_orders,
        count(case when is_completed then 1 end)            as completed_orders,
        count(case when is_returned  then 1 end)            as returned_orders,
        count(case when is_cancelled then 1 end)            as cancelled_orders,

        sum(case when is_completed then order_amount end)   as lifetime_value,
        avg(case when is_completed then order_amount end)   as avg_order_value,
        max(case when is_completed then order_amount end)   as max_order_value,

        min(order_placed_at)                                as first_order_at,
        max(order_placed_at)                                as most_recent_order_at,
        min(order_date)                                     as first_order_date,

        -- Days between first and most recent order (customer lifespan)
        max(order_date) - min(order_date)                   as customer_lifespan_days,

        -- Customer tier based on LTV
        case
            when sum(case when is_completed then order_amount end) >= 200 then 'vip'
            when sum(case when is_completed then order_amount end) >= 100 then 'regular'
            when sum(case when is_completed then order_amount end) >  0   then 'new'
            else 'never_purchased'
        end                                                 as customer_tier

    from orders
    group by 1

)

select * from customer_orders
