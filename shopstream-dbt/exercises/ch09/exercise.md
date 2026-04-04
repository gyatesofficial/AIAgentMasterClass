# Chapter 9 Exercise: Snapshots

## Exercise 9.1 — Inspect the Snapshot
Run `dbt snapshot` to create the `customer_snapshot` table. Query it directly
in your warehouse and examine the `dbt_valid_from`, `dbt_valid_to`, and
`dbt_scd_id` columns.

How many rows are there? Why (even though no data has changed yet)?

## Exercise 9.2 — Simulate a Change
Manually UPDATE a row in `raw.customers` — change customer_id=1's country from `US` to `CA`.
Run `dbt snapshot` again. Query the snapshot:
- How many rows exist for customer_id=1?
- What is `dbt_valid_to` on the old row?
- What is `dbt_valid_from` on the new row?

Roll back your manual change and run `dbt snapshot` a third time.
What happens?

## Exercise 9.3 — Check Strategy
Create a second snapshot `snapshots/product_snapshot.sql` using the **check** strategy
instead of timestamp. Track changes to `unit_price_cents` and `is_active`.

The check strategy config looks like:
```
strategy   = 'check',
check_cols = ['unit_price_cents', 'is_active'],
```

## Exercise 9.4 — Downstream of Snapshots (Stretch)
Create a staging model `stg_customer_history.sql` that reads from
`{{ ref('customer_snapshot') }}` and adds an `is_current` boolean
(`dbt_valid_to is null`). Use this to answer: "How many customers
have ever changed their country?"
