# ShopStream dbt Project
### Companion repository for *dbt Zero to Hero*

This is the hands-on companion project for the course. ShopStream is a fictional
e-commerce company whose data you'll use to learn every major dbt concept — from
your first `dbt run` to production CI/CD pipelines.

---

## Quick Start

**1. Clone and install dbt**
```bash
# Install dbt Core with your adapter of choice
pip install dbt-postgres     # or dbt-bigquery / dbt-snowflake / dbt-duckdb
```

**2. Configure your profile**
```bash
cp profiles.yml.example ~/.dbt/profiles.yml
# Edit ~/.dbt/profiles.yml with your warehouse credentials
# Or set environment variables: DBT_USER, DBT_PASSWORD
```

**3. Install packages and load seed data**
```bash
dbt deps          # install dbt_utils, dbt_expectations, codegen
dbt seed          # load the sample CSV data into raw.*  tables
```

**4. Build the project**
```bash
dbt build         # runs models + tests in DAG order
```

**5. Generate documentation**
```bash
dbt docs generate
dbt docs serve    # opens http://localhost:8080
```

---

## Project Structure

```
shopstream-dbt/
├── dbt_project.yml          # Project configuration
├── packages.yml             # Package dependencies
├── profiles.yml.example     # Profile template (copy to ~/.dbt/)
│
├── seeds/                   # Sample CSV data (raw source tables)
│   ├── raw_customers.csv
│   ├── raw_orders.csv
│   ├── raw_order_items.csv
│   ├── raw_products.csv
│   └── raw_payments.csv
│
├── models/
│   ├── staging/             # Layer 1: 1-to-1 with sources
│   │   ├── _sources.yml
│   │   ├── _staging.yml
│   │   ├── stg_customers.sql
│   │   ├── stg_orders.sql
│   │   ├── stg_order_items.sql
│   │   ├── stg_products.sql
│   │   └── stg_payments.sql
│   │
│   ├── intermediate/        # Layer 2: complex joins (ephemeral)
│   │   ├── int_orders_with_payments.sql
│   │   └── int_customer_order_history.sql
│   │
│   └── marts/               # Layer 3: BI-ready tables
│       ├── core/
│       │   ├── _core.yml
│       │   ├── dim_customers.sql
│       │   ├── dim_products.sql
│       │   └── fct_orders.sql
│       └── finance/
│           └── fct_revenue_daily.sql  ← incremental model
│
├── snapshots/               # SCD Type 2 history tracking
│   └── customer_snapshot.sql
│
├── macros/                  # Reusable Jinja macros
│   ├── cents_to_dollars.sql
│   ├── generate_schema_name.sql
│   ├── date_spine.sql
│   └── test_is_positive.sql  ← custom generic test
│
├── tests/                   # Singular tests
│   └── assert_payments_match_order_items.sql
│
├── analyses/                # Ad-hoc compiled SQL (not persisted)
│   └── cohort_retention.sql
│
├── docs/                    # doc blocks
│   └── overview.md
│
└── exercises/               # Chapter exercises
    ├── ch04/  ch05/  ch06/  ch07/
    ├── ch08/  ch09/  ch10/  ch11/  ch12/
```

---

## Data Model

```
raw_customers ──┐
                ├──► stg_customers ──────────────────────────► dim_customers
                │                                                    │
raw_orders ─────┤                                                    │
                ├──► stg_orders ────► int_orders_with_payments ──► fct_orders
                │                        │
raw_payments ───┘                        │
                                         └──► fct_revenue_daily (incremental)
raw_order_items ──► stg_order_items ─────────────────────────► fct_orders
                                    ──────────────────────────► dim_products

raw_products ──────► stg_products ───────────────────────────► dim_products
```

---

## Chapter Reference

| Chapter | Key Files |
|---------|-----------|
| 4 — Materializations | `stg_customers.sql`, `fct_revenue_daily.sql` |
| 5 — Sources & Seeds | `_sources.yml`, `seeds/` |
| 6 — Tests & Docs | `_staging.yml`, `_core.yml`, `tests/` |
| 7 — ref() & DAG | All models — run `dbt docs serve` |
| 8 — Macros | `macros/` |
| 9 — Snapshots | `snapshots/customer_snapshot.sql` |
| 10 — Incremental | `fct_revenue_daily.sql` |
| 11 — Packages | `packages.yml`, `dbt_utils` usage in `_sources.yml` |
| 12 — CI/CD | `exercises/ch12/exercise.md` |
