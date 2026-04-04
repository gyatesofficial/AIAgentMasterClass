-- fct_revenue_daily.sql
-- Daily revenue summary. Demonstrates an INCREMENTAL model.
-- On the first run (full refresh), builds the entire history.
-- On subsequent runs, only processes new/changed orders.

{{
  config(
    materialized = 'incremental',
    unique_key   = 'revenue_date',        -- one row per date — upsert by date
    incremental_strategy = 'merge',
    tags         = ['finance', 'daily'],
    on_schema_change = 'sync_all_columns'
  )
}}

with orders as (

    select * from {{ ref('fct_orders') }}

    {% if is_incremental() %}
        -- On incremental runs: only process orders from the past 3 days
        -- (3 days covers late-arriving data — orders finalized after day-end)
        where order_date >= (select max(revenue_date) - interval '3 days' from {{ this }})
    {% endif %}

),

daily_agg as (

    select
        order_date                                  as revenue_date,

        -- Counts
        count(*)                                    as total_orders,
        count(case when is_completed  then 1 end)   as completed_orders,
        count(case when is_returned   then 1 end)   as returned_orders,
        count(case when is_cancelled  then 1 end)   as cancelled_orders,

        -- Revenue
        sum(case when is_completed then revenue else 0 end) as gross_revenue,
        sum(case when is_returned  then revenue else 0 end) as refunded_revenue,
        sum(case when is_completed then revenue else 0 end)
          - sum(case when is_returned then revenue else 0 end) as net_revenue,

        -- Customers
        count(distinct customer_id)                 as unique_customers,

        -- Average order value (completed only)
        avg(case when is_completed then revenue end) as avg_order_value,

        -- Payment method mix
        count(case when payment_method = 'credit_card'   then 1 end) as credit_card_orders,
        count(case when payment_method = 'paypal'        then 1 end) as paypal_orders,
        count(case when payment_method = 'bank_transfer' then 1 end) as bank_transfer_orders,
        count(case when payment_method = 'gift_card'     then 1 end) as gift_card_orders

    from orders
    group by 1

)

select * from daily_agg
