-- int_orders_with_payments.sql
--
-- Intermediate model: joins orders to their payments.
-- Intermediate models live in the "ephemeral" materialization by default
-- (they become CTEs inlined into downstream models — no warehouse object created).
-- Use them to encapsulate complex business logic without polluting the mart layer.

with orders as (

    select * from {{ ref('stg_orders') }}

),

payments as (

    select * from {{ ref('stg_payments') }}

),

-- Aggregate payments per order — we want one row per order
order_payments as (

    select
        order_id,

        -- Successful payment
        max(case when is_successful then amount     end) as payment_amount,
        max(case when is_successful then amount_cents end) as payment_amount_cents,
        max(case when is_successful then payment_method end) as payment_method,
        max(case when is_successful then paid_at    end) as paid_at,

        -- Counts by status
        sum(case when is_successful then 1 else 0 end)  as successful_payment_count,
        sum(case when is_failed     then 1 else 0 end)  as failed_payment_count,
        sum(case when is_refunded   then 1 else 0 end)  as refund_count,

        -- Was this order ever successfully paid?
        max(is_successful::int)::boolean                as has_successful_payment

    from payments
    group by 1

),

joined as (

    select
        orders.*,
        coalesce(op.payment_amount, 0)              as order_amount,
        coalesce(op.payment_amount_cents, 0)        as order_amount_cents,
        op.payment_method,
        op.paid_at,
        coalesce(op.has_successful_payment, false)  as has_successful_payment,
        coalesce(op.failed_payment_count, 0)        as failed_payment_count,
        coalesce(op.refund_count, 0)                as refund_count

    from orders
    left join order_payments op using (order_id)

)

select * from joined
