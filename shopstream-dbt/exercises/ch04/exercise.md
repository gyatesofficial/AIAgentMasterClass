# Chapter 4 Exercise: Materializations

## Setup
Ensure you have run `dbt seed` to load the sample data.

## Exercise 4.1 — Your First Model (View)
Create `models/staging/stg_order_items.sql` from scratch using the source
`shopstream_raw.order_items`. Requirements:
- Rename `id` → `order_item_id`
- Cast `quantity` to integer and `unit_price_cents` to integer
- Add a `line_total_cents` calculated column (`quantity * unit_price_cents`)
- Materialize as a **view**

Run it: `dbt run --select stg_order_items`

## Exercise 4.2 — Table vs View
Change `stg_customers` to a **table** materialization using an in-file config block.
Run `dbt run --select stg_customers` twice and observe the difference in run time
and warehouse storage in your query history.

Then change it back to a view (tables are wasteful for staging).

## Exercise 4.3 — Ephemeral
Create a new intermediate model `int_order_totals.sql` that aggregates
`stg_order_items` to one row per `order_id` with columns:
- `order_id`
- `total_line_items`
- `order_subtotal_cents`
- `order_subtotal`

Set its materialization to `ephemeral`. Confirm that running it does NOT
create any object in the warehouse (`dbt run --select int_order_totals`
should succeed but create nothing).

## Exercise 4.4 — Incremental (Stretch)
Look at `fct_revenue_daily.sql` in the `marts/finance/` folder.
Modify it to add a `by_country` breakdown — add a `shipping_country_code`
column and change `unique_key` to `['revenue_date', 'shipping_country_code']`.

Run `dbt run --select fct_revenue_daily` for a full refresh, then run again
and check the query logs to confirm only 3 days of data were reprocessed.
