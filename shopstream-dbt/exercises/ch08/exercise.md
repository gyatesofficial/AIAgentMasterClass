# Chapter 8 Exercise: Jinja & Macros

## Exercise 8.1 — Jinja Variables
In `stg_payments.sql`, replace the hardcoded string `'credit_card'` in the
`payment_method` status boolean with a reference to `var('payment_methods')`.
The expression should check if `payment_method` is in the list.

Hint: Jinja's `in` operator works on lists.

## Exercise 8.2 — Write a Macro
Write a macro `macros/safe_divide.sql` that performs division but returns
`null` instead of dividing by zero. Signature:
```sql
{{ safe_divide(numerator, denominator) }}
```

Use it in a new column `return_rate` in `dim_customers`:
```
returned_orders / completed_orders
```

## Exercise 8.3 — Dynamic SQL with Macros
Write a macro `macros/union_tables.sql` that accepts a list of table names
and generates a UNION ALL query across all of them. Test it in an analysis file.

## Exercise 8.4 — Macro with Dispatch (Stretch)
Create a macro `macros/current_timestamp.sql` that uses `adapter.type()`
to return the correct current-timestamp function for your database adapter:
- postgres/redshift: `now()`
- bigquery: `current_timestamp()`
- snowflake: `convert_timezone('UTC', current_timestamp())`
