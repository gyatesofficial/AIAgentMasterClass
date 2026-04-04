-- cohort_retention.sql
-- Classic monthly cohort retention analysis.
-- Not a model — this is an ad-hoc analysis that compiles but doesn't persist.
-- Run with: dbt compile --select analyses/cohort_retention
-- Then execute the compiled SQL directly in your warehouse.

with cohorts as (

    select
        customer_id,
        signup_month                                        as cohort_month

    from {{ ref('dim_customers') }}
    where first_order_at is not null   -- only customers who actually ordered

),

orders as (

    select
        customer_id,
        order_month,
        count(*) as orders_in_month

    from {{ ref('fct_orders') }}
    where is_completed
    group by 1, 2

),

cohort_activity as (

    select
        c.cohort_month,
        o.order_month,

        -- Month index: 0 = acquisition month, 1 = first retention month, etc.
        (date_part('year',  o.order_month) - date_part('year',  c.cohort_month)) * 12
        + (date_part('month', o.order_month) - date_part('month', c.cohort_month))
            as month_number,

        count(distinct c.customer_id)   as active_customers

    from cohorts c
    inner join orders o using (customer_id)
    group by 1, 2, 3

),

cohort_sizes as (

    select cohort_month, count(*) as cohort_size
    from cohorts
    group by 1

)

select
    ca.cohort_month,
    cs.cohort_size,
    ca.month_number,
    ca.active_customers,
    round(ca.active_customers::numeric / cs.cohort_size * 100, 1) as retention_pct

from cohort_activity ca
join cohort_sizes cs using (cohort_month)
order by cohort_month, month_number
