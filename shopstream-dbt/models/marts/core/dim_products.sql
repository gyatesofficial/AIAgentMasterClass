{{
  config(materialized='table', tags=['core', 'weekly'])
}}

with products as (

    select * from {{ ref('stg_products') }}

),

product_sales as (

    select
        oi.product_id,
        count(distinct oi.order_id)     as times_ordered,
        sum(oi.quantity)                as units_sold,
        sum(oi.line_total)              as total_revenue

    from {{ ref('stg_order_items') }} oi
    inner join {{ ref('stg_orders') }} o using (order_id)
    where o.status = 'completed'
    group by 1

),

final as (

    select
        p.product_id,
        p.product_name,
        p.category,
        p.sku,
        p.unit_price,
        p.unit_price_cents,
        p.is_active,
        p.introduced_on,
        coalesce(ps.times_ordered, 0)   as times_ordered,
        coalesce(ps.units_sold, 0)      as units_sold,
        coalesce(ps.total_revenue, 0)   as total_revenue

    from products p
    left join product_sales ps using (product_id)

)

select * from final
