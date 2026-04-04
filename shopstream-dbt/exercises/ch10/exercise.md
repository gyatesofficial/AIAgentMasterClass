# Chapter 10 Exercise: Incremental Models

## Exercise 10.1 — Build the Incremental Model
Run `dbt run --select fct_revenue_daily --full-refresh`. Check your warehouse
query logs to confirm the full dataset was processed.

Now run `dbt run --select fct_revenue_daily` (no flag). Check the logs —
only 3 recent days should have been processed.

## Exercise 10.2 — Add a Column Safely
Add a new column `new_customers` to `fct_revenue_daily`:
```sql
count(distinct case when is_completed and customer_tier_at_order = 'new'
                    then customer_id end) as new_customers
```

Run with `--full-refresh`. What happens if you run WITHOUT `--full-refresh`?
Set `on_schema_change = 'sync_all_columns'` and try again.

## Exercise 10.3 — Append Strategy
Create a new incremental model `models/marts/finance/fct_payments_log.sql`
using the `append` strategy (no unique_key). Each row is an immutable
payment event — append is safe because payments never change.

Config:
```
materialized = 'incremental',
incremental_strategy = 'append'
```

Filter using `paid_at >= (select max(paid_at) from {{ this }})`.

## Exercise 10.4 — Incremental Predicates (Stretch)
Add `incremental_predicates` to `fct_revenue_daily` to restrict the merge
to only the last 7 days in the target table (prevents full table scans
on partitioned tables):

```python
incremental_predicates = [
    "dbt_internal_dest.revenue_date >= current_date - interval '7 days'"
]
```
