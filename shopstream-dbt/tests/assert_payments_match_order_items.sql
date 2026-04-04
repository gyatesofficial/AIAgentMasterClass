-- Singular test: assert that for every completed order,
-- the successful payment amount matches the sum of order item line totals.
-- Tolerates a ±1 cent rounding difference.
--
-- Returns rows that FAIL the assertion (dbt fails the test if any rows are returned).

with order_item_totals as (

    select
        order_id,
        sum(line_total_cents) as items_total_cents

    from {{ ref('stg_order_items') }}
    group by 1

),

payments as (

    select
        order_id,
        amount_cents as payment_amount_cents

    from {{ ref('stg_payments') }}
    where is_successful

),

orders as (

    select order_id
    from {{ ref('stg_orders') }}
    where status = 'completed'

)

select
    o.order_id,
    oi.items_total_cents,
    p.payment_amount_cents,
    abs(oi.items_total_cents - p.payment_amount_cents) as discrepancy_cents

from orders o
join order_item_totals oi using (order_id)
join payments p using (order_id)

-- Fail if discrepancy is more than 1 cent (rounding tolerance)
where abs(oi.items_total_cents - p.payment_amount_cents) > 1
