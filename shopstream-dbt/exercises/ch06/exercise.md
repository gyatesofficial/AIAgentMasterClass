# Chapter 6 Exercise: Testing & Documentation

## Exercise 6.1 — Add Generic Tests
Open `models/staging/_staging.yml`. Add the following tests that are currently missing:
- `stg_products`: `product_id` unique + not_null, `unit_price_cents` must be > 0 (use `dbt_utils.expression_is_true`)
- `stg_payments`: `amount_cents` must be ≥ 0

Run `dbt test --select staging` and fix any failures you find.

## Exercise 6.2 — Write a Singular Test
Create `tests/assert_no_negative_revenue.sql`.
It should return rows from `fct_orders` where `revenue < 0`.
Run `dbt test --select assert_no_negative_revenue` to verify it passes.

## Exercise 6.3 — Write a Custom Generic Test
In `macros/test_is_positive.sql` you'll find a skeleton for a generic test.
Complete the implementation, then apply it to `quantity` in `stg_order_items`.

## Exercise 6.4 — Documentation
Add `description` fields to **every column** in `models/staging/_staging.yml`
for `stg_orders` (it currently has none).

Run `dbt docs generate && dbt docs serve` and verify your descriptions
appear in the documentation site.

## Exercise 6.5 — Doc Blocks
Create a `docs/` directory and a file `docs/metrics.md`. Write a `{% docs %}` block
that explains what "revenue" means for ShopStream. Reference it from
the `revenue` column description in `_core.yml` using `'{{ doc("...") }}'`.
