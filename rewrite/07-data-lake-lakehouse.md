# Module 7: Data Quality & Testing

*The #1 thing that separates a junior DE from a senior one: the senior one checks their work. I've seen bad data cost companies millions in wrong business decisions. This module is about making sure that never happens on your watch.*

---

## 7.1 Why Data Quality Is Your Job (Not the Analyst's)

> **TL;DR:** Data quality is the data engineer's responsibility because you control the pipeline. Silent failures -- not crashes -- are the #1 way data engineers lose credibility. Build quality checks into every stage, not just at the end.

### The Silent Killer

Picture this. It's 9:15 AM on a Monday. Your VP of Sales opens their dashboard, sees revenue dropped 40% over the weekend, panics, fires off an email to the CEO. By 9:30 the CEO is pinging your manager. By 10 AM your manager is pinging you. And what happened? A third-party API changed their date format from `YYYY-MM-DD` to `MM/DD/YYYY` and your pipeline silently ingested garbage all weekend.

Nobody's pipeline crashed. No errors in the logs. The data just... went bad. And nobody knew until someone looked at a dashboard two days later.

**At your job, this will happen to you.** Your pipeline ran successfully. Airflow is green. But the CEO's dashboard shows revenue dropped 90% overnight. What happened? A source API changed its schema, and your pipeline happily loaded the mangled data without a single error. This is the #1 way data engineers lose credibility. Not because of downtime -- because of *silent failures*.

> **Key Concept: Silent Failures**
> A silent failure is when your pipeline runs successfully (no errors, exit code 0) but produces incorrect data. These are far more dangerous than crashes because nobody knows anything is wrong until downstream consumers notice bad numbers.

### The Six Categories of Data Quality Issues

Every data quality issue you'll encounter in the real world falls into one of these categories:

1. **Schema drift** -- upstream source adds, removes, or renames columns
2. **Completeness** -- missing values, nulls where there shouldn't be any. NULL foreign keys = broken JOINs. If `customer_id` is NULL, your entire customer attribution model falls apart.
3. **Freshness** -- data is stale; the pipeline didn't run or ran late. Stale data = wrong dashboards. If your dashboard shows yesterday's numbers but doesn't tell anyone, decisions get made on old information.
4. **Accuracy** -- values are present but wrong (duplicates, bad calculations)
5. **Consistency** -- the same entity has different values in different tables
6. **Volume anomalies** -- suddenly getting 10x or 0.1x the normal row count. Sudden drops = broken upstream. If you normally get 10,000 orders a day and suddenly get 50, something is very wrong even if there are no errors.

The nasty part? Most of these don't show up as errors. They show up as *wrong numbers in dashboards* weeks later.

### Real-World Horror Stories

These are from real companies:

- **Fintech startup:** Loaded duplicate transactions for 3 weeks because their deduplication key changed upstream. Cost: $2M in misreported revenue.
- **E-commerce company:** Product dimension table got a column renamed from `category` to `product_category`. Joins silently returned NULLs. Nobody noticed for 5 days.
- **Healthcare company:** Date parsing silently converted European dates (DD/MM/YYYY) to American (MM/DD/YYYY). Patient records got wrong dates for months.

Every single one of these was preventable with basic data quality checks.

### The Ownership Model

"Isn't data quality the data team's problem? Like, shouldn't the analysts check their own stuff?"

No. Here's why: you, the data engineer, control the pipeline. You decide what gets loaded, how it gets transformed, and where it lands. If bad data gets through, it's because your pipeline let it through. You're the gatekeeper.

Think of it as defense in depth:

| Layer | Owner | What It Checks |
|-------|-------|----------------|
| **Layer 1: Pipeline-level** | Data Engineer | Schema validation, null checks, freshness, volume |
| **Layer 2: Transformation-level** | Data Engineer | Business logic validation, referential integrity |
| **Layer 3: Dashboard-level** | Analyst | Metric validation, trend analysis |

You own Layers 1 and 2.

> **Common Mistake:** The biggest mistake: adding data quality checks *after* an incident (reactive, not proactive). Build them in from day one. The second biggest: only checking the happy path. Your checks need to catch *unexpected* data, not just validate expected data.

### Checkpoint

1. What's the difference between a pipeline failure and a silent failure? Which is more dangerous and why?
2. Name the six categories of data quality issues.
3. Which layers of the data quality defense model are the data engineer's responsibility?

---

## 7.2 Types of Data Quality Checks

> **TL;DR:** There are six core categories of data quality checks: schema validation, completeness, freshness, accuracy, consistency, and volume anomalies. You can't check everything -- be strategic about which checks you implement for each table.

You're convinced data quality matters. But what do you actually *check*? You can't check everything -- that would make your pipeline take 10x longer. You need to be strategic.

Here are the exact checks to add to every pipeline, with real SQL running against our e-commerce tables.

### 1. Schema Validation

Before you even load data, check that it looks like what you expect.

```sql
-- Check column count and names match expected schema
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'raw_orders'
ORDER BY ordinal_position;
```

In Python, validate *before* the data touches the database:

```python
import pandas as pd

# Define the contract for what the data should look like
EXPECTED_COLUMNS = {
    'order_id': 'int64',
    'customer_id': 'int64',
    'order_date': 'datetime64[ns]',
    'total_amount': 'float64',
    'status': 'object',
}

def validate_schema(df: pd.DataFrame) -> bool:
    """Validate DataFrame matches expected schema."""
    missing = set(EXPECTED_COLUMNS.keys()) - set(df.columns)
    extra = set(df.columns) - set(EXPECTED_COLUMNS.keys())

    if missing:
        raise ValueError(f"Missing columns: {missing}")
    if extra:
        # Don't fail on extra columns -- but log it
        print(f"WARNING: Extra columns detected: {extra}")

    # Check types
    for col, expected_type in EXPECTED_COLUMNS.items():
        actual_type = str(df[col].dtype)
        if actual_type != expected_type:
            raise TypeError(
                f"Column '{col}' expected {expected_type}, got {actual_type}"
            )

    return True
```

**Expected output (when validation passes):**

```
True
```

**Expected output (when a column is missing):**

```
ValueError: Missing columns: {'customer_id'}
```

### 2. Completeness Checks

Are there nulls where there shouldn't be any?

```sql
-- Null check for critical columns
SELECT
    COUNT(*) AS total_rows,
    COUNT(*) - COUNT(order_id) AS null_order_ids,
    COUNT(*) - COUNT(customer_id) AS null_customer_ids,
    COUNT(*) - COUNT(order_date) AS null_order_dates,
    COUNT(*) - COUNT(total_amount) AS null_amounts
FROM raw_orders
WHERE loaded_at >= CURRENT_DATE;  -- Only check today's load
```

**Expected output:**

```
 total_rows | null_order_ids | null_customer_ids | null_order_dates | null_amounts
------------+----------------+-------------------+------------------+--------------
       1523 |              0 |                 0 |                0 |           12
```

> **Key Concept: Not All Nulls Are Bad**
> A `shipping_date` being null is perfectly fine if the order hasn't shipped yet. But an `order_id` being null? That's a hard failure. Define your null-tolerance rules per column.

### 3. Freshness Checks

Is the data actually current?

```sql
-- Check that we have data from the expected time window
SELECT
    MAX(order_date) AS most_recent_order,
    NOW() - MAX(order_date) AS data_lag,
    CASE
        WHEN NOW() - MAX(order_date) > INTERVAL '2 hours'
        THEN 'STALE'
        ELSE 'FRESH'
    END AS freshness_status
FROM raw_orders;
```

**Expected output:**

```
    most_recent_order     |    data_lag    | freshness_status
--------------------------+----------------+------------------
 2026-02-19 14:32:11+00   | 00:45:22       | FRESH
```

Freshness checks fail when: upstream systems are down, your scheduler skipped a run, or there's a network issue. Freshness is often the *first* signal that something's wrong.

### 4. Accuracy / Validity Checks

Do the values make sense?

```sql
-- Range checks
SELECT COUNT(*) AS invalid_amounts
FROM raw_orders
WHERE total_amount < 0
   OR total_amount > 100000;  -- No single order should be > $100K

-- Enum/category validation
SELECT status, COUNT(*)
FROM raw_orders
WHERE status NOT IN ('pending', 'processing', 'shipped', 'delivered', 'cancelled')
GROUP BY status;
-- Any rows here = unexpected status values

-- Date sanity
SELECT COUNT(*) AS future_orders
FROM raw_orders
WHERE order_date > NOW();  -- Orders from the future = bad data

-- Referential integrity
SELECT o.order_id
FROM raw_orders o
LEFT JOIN dim_customers c ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL;
-- Orphaned orders = customer data missing or mismatched
```

### 5. Consistency Checks

Does the same thing look the same everywhere?

```sql
-- Cross-table consistency
SELECT
    (SELECT SUM(total_amount) FROM fact_orders WHERE order_date = '2026-02-18') AS fact_total,
    (SELECT SUM(total_amount) FROM raw_orders WHERE order_date::date = '2026-02-18') AS raw_total;
-- These should match (or be within acceptable rounding tolerance)

-- Unique constraint validation
SELECT order_id, COUNT(*) AS dupes
FROM fact_orders
GROUP BY order_id
HAVING COUNT(*) > 1;
-- Any results = duplicates in your fact table. Bad.
```

### 6. Volume Anomaly Detection

Did we get a reasonable amount of data?

```sql
-- Compare today's volume against a rolling 30-day average
WITH daily_volumes AS (
    SELECT
        order_date::date AS load_date,
        COUNT(*) AS row_count
    FROM raw_orders
    WHERE order_date >= CURRENT_DATE - INTERVAL '30 days'
    GROUP BY order_date::date
),
stats AS (
    SELECT
        AVG(row_count) AS avg_count,
        STDDEV(row_count) AS stddev_count
    FROM daily_volumes
    WHERE load_date < CURRENT_DATE
)
SELECT
    dv.load_date,
    dv.row_count,
    s.avg_count,
    CASE
        WHEN dv.row_count < s.avg_count - 2 * s.stddev_count THEN 'ANOMALY_LOW'
        WHEN dv.row_count > s.avg_count + 2 * s.stddev_count THEN 'ANOMALY_HIGH'
        ELSE 'NORMAL'
    END AS volume_status
FROM daily_volumes dv, stats s
WHERE dv.load_date = CURRENT_DATE;
```

**Expected output:**

```
  load_date   | row_count | avg_count | volume_status
--------------+-----------+-----------+---------------
 2026-02-19   |      1523 |    1480.3 | NORMAL
```

This check catches the "pipeline ran but loaded 0 rows" problem. If you're getting 10,000 orders a day and suddenly get 50, something is wrong even if there are no errors.

> **Common Mistake:**
> - Checking only for nulls and calling it "data quality." That's maybe 20% of what you need.
> - Hard-coding thresholds instead of using statistical baselines. What's "normal" changes over time.
> - Running checks *after* the data hits the warehouse. Run them *before* or *during* loading so you can reject bad batches.

> **Pro Tip:** Start with the checks most likely to catch real problems at your company. For most teams, that's: null checks on PKs, freshness, and volume anomalies. You can add more as you discover issues.

### Checkpoint

1. Write a SQL query that checks for duplicate `order_id` values in a `raw_orders` table.
2. Why is a volume anomaly check better than a simple "row count > 0" check?
3. What's the difference between an accuracy check and a consistency check?

---

## 7.3 Great Expectations & Soda -- Automated Data Quality Frameworks

> **TL;DR:** Great Expectations (GX) and Soda let you define data quality checks as config instead of hand-written SQL. GX is the industry standard with powerful features and auto-generated reports. Soda is simpler and YAML-driven. Use whichever fits your team.

Writing SQL checks by hand for every table gets old fast when you have 50 tables and 200 columns. Data quality frameworks let you define checks as config, run them automatically, and generate reports.

### Great Expectations Setup

```bash
pip install great_expectations
great_expectations init
```

This creates a project structure:

```
great_expectations/
  great_expectations.yml    # Main config
  expectations/             # Your expectation suites (the checks)
  checkpoints/              # How and when to run checks
  plugins/                  # Custom expectations
  uncommitted/
    config_variables.yml    # Secrets (don't commit this)
    data_docs/              # Generated HTML reports
```

### Connecting to Your Data

```python
import great_expectations as gx

context = gx.get_context()

# Add a Postgres datasource
datasource = context.sources.add_postgres(
    name="postgres_db",
    connection_string="postgresql+psycopg2://postgres:postgres@localhost:5432/ecommerce",
)

# Add a data asset (table)
data_asset = datasource.add_table_asset(
    name="raw_orders",
    table_name="raw_orders",
)

# Create a batch request (what data to validate)
batch_request = data_asset.build_batch_request()
```

### Writing Expectations

Expectations are the checks themselves -- assertions for your data that read like English:

```python
# Create an expectation suite
suite = context.add_expectation_suite("raw_orders_suite")

# Get a validator -- connects the suite to actual data
validator = context.get_validator(
    batch_request=batch_request,
    expectation_suite_name="raw_orders_suite",
)

# Schema checks
validator.expect_table_columns_to_match_ordered_list(
    column_list=["order_id", "customer_id", "order_date", "total_amount", "status"]
)

# Null checks
validator.expect_column_values_to_not_be_null(column="order_id")
validator.expect_column_values_to_not_be_null(column="customer_id")
validator.expect_column_values_to_not_be_null(column="order_date")

# Allow some nulls in total_amount (e.g., pending orders)
validator.expect_column_values_to_not_be_null(
    column="total_amount",
    mostly=0.95,  # At least 95% non-null
)

# Value ranges
validator.expect_column_values_to_be_between(
    column="total_amount",
    min_value=0,
    max_value=100000,
)

# Valid categories
validator.expect_column_values_to_be_in_set(
    column="status",
    value_set=["pending", "processing", "shipped", "delivered", "cancelled"],
)

# Uniqueness
validator.expect_column_values_to_be_unique(column="order_id")

# Row count within expected range
validator.expect_table_row_count_to_be_between(
    min_value=1000,
    max_value=500000,
)

# No future dates
validator.expect_column_values_to_be_between(
    column="order_date",
    max_value="2026-02-20",  # Today + 1 day buffer
)

# Save the suite
validator.save_expectation_suite(discard_failed_expectations=False)
```

### Running Validations via Checkpoints

Expectations don't do anything until you run them. Checkpoints handle execution:

```python
checkpoint = context.add_or_update_checkpoint(
    name="raw_orders_checkpoint",
    validations=[
        {
            "batch_request": batch_request,
            "expectation_suite_name": "raw_orders_suite",
        },
    ],
)

# Run it
result = checkpoint.run()

# Check if everything passed
if not result.success:
    for validation_result in result.run_results.values():
        for expectation_result in validation_result["validation_result"]["results"]:
            if not expectation_result["success"]:
                print(f"FAILED: {expectation_result['expectation_config']['expectation_type']}")
                print(f"  Details: {expectation_result['result']}")
    raise Exception("Data quality checks failed!")
else:
    print("All data quality checks passed!")
```

**Expected output (all passing):**

```
All data quality checks passed!
```

### Data Docs -- Auto-Generated Reports

One of GX's killer features:

```python
context.build_data_docs()
context.open_data_docs()
```

This opens a browser with a report showing every expectation, whether it passed or failed, with details. When an analyst asks "how do you know the data is good?" you send them the Data Docs link.

> **Pro Tip:** Data Docs are a great way to build trust with stakeholders. Set up automated publishing so the latest quality report is always available at a known URL.

### Soda -- The Simpler Alternative

Soda is YAML-based and simpler for basic checks:

```bash
pip install soda-core-postgres
```

Create `checks/raw_orders.yml` :

```yaml
checks for raw_orders:
  - row_count > 0
  - missing_count(order_id) = 0
  - missing_count(customer_id) = 0
  - missing_percent(total_amount) < 5%
  - duplicate_count(order_id) = 0
  - min(total_amount) >= 0
  - max(total_amount) <= 100000
  - invalid_count(status) = 0:
      valid values: ['pending', 'processing', 'shipped', 'delivered', 'cancelled']
  - freshness(order_date) < 2d
  - anomaly detection for row_count
```

Soda configuration (`configuration.yml`):

```yaml
data_source ecommerce:
  type: postgres
  host: localhost
  port: 5432
  username: postgres
  password: postgres
  database: ecommerce
```

Run it:

```bash
soda scan -d ecommerce -c configuration.yml checks/raw_orders.yml
```

Soda is great for teams that want something quick and YAML-driven. Great Expectations is more powerful and flexible, especially for complex checks and Airflow integration. Use whichever fits your team.

**See companion code:** The `soda/` directory in the module-7 project contains working Soda check files and configuration.

> `de-fast-track/modules/module-7/solution/soda/checks/raw_orders.yml`
> `de-fast-track/modules/module-7/solution/soda/configuration.yml`

> **Common Mistake:**
> - Writing 200 expectations for every table. Start with the critical checks and add more as you discover issues.
> - Not versioning your expectation suites. They're config -- they belong in Git.
> - Running GX checks but not failing the pipeline when they fail. If you don't stop bad data, the checks are pointless.

### Checkpoint

1. What's the difference between an expectation suite and a checkpoint in Great Expectations?
2. When would you choose Soda over Great Expectations?
3. What does the `mostly=0.95` parameter do in a null check expectation?

---

## 7.4 dbt Tests and Custom Test Macros

> **TL;DR:** Great Expectations checks your raw data. dbt tests validate your *transformation logic* -- ensuring your SQL produces correct results and your business rules hold. dbt has generic tests (unique, not_null, relationships) and custom tests (any SQL that returns failing rows).

Great Expectations checks your raw data. But what about the *transformations*? What if your SQL that calculates revenue is wrong? What if your join produces duplicates? That's where dbt tests come in.

**The dbt testing philosophy: test your assumptions, not your transformations.** You don't need to test that `SELECT` works. You need to test that `order_id` is actually unique, that every order has a valid customer, and that revenue is never negative. You're testing what *should* be true about your data, and catching the cases where reality disagrees.

> **Interview angle:** When they ask "how do you ensure data quality," here's the framework: "I use a layered approach. Data contracts validate schema at ingestion. Great Expectations or Soda checks raw data quality -- nulls, freshness, volume anomalies. dbt tests validate transformation logic -- referential integrity, business rules, uniqueness constraints. And I have alerting so I know within minutes when something breaks, not days."

### Generic Tests

In your `schema.yml`:

```yaml
version: 2
models:
  - name: stg_orders
    description: "Staged orders from raw source"
    columns:
      - name: order_id
        description: "Unique order identifier"
        tests:
          - not_null
          - unique
      - name: customer_id
        tests:
          - not_null
          - relationships:
              to: ref('stg_customers')
              field: customer_id
      - name: order_date
        tests:
          - not_null
      - name: status
        tests:
          - accepted_values:
              values: ['pending', 'completed', 'returned', 'cancelled']
      - name: total_amount
        tests:
          - not_null
  - name: stg_customers
    description: "Staged customers"
    columns:
      - name: customer_id
        tests:
          - not_null
          - unique
      - name: segment
        tests:
          - accepted_values:
              values: ['Enterprise', 'SMB', 'Consumer']
```

**See companion code:** The starter and solution `schema.yml` files are in the module-7 project:

> `de-fast-track/modules/module-7/starter/dbt/schema.yml` (with TODOs)
> `de-fast-track/modules/module-7/solution/dbt/schema.yml` (complete)

```bash
dbt test
```

**Expected output:**

```
Completed successfully

Pass: 7  Warn: 0  Error: 0  Skip: 0  Total: 7
```

### Custom Tests

Real business logic needs custom tests. Create files in `tests/` -- a failing test returns rows, and zero rows means pass.

**`tests/assert_order_total_matches_line_items.sql`:**

```sql
-- Fails if ANY order's total doesn't match its line items sum
SELECT
    o.order_id,
    o.total_amount AS order_total,
    SUM(oi.quantity * oi.unit_price - oi.discount) AS calculated_total,
    ABS(o.total_amount - SUM(oi.quantity * oi.unit_price - oi.discount)) AS difference
FROM {{ ref('stg_orders') }} o
JOIN {{ ref('stg_order_items') }} oi ON o.order_id = oi.order_id
GROUP BY o.order_id, o.total_amount
HAVING ABS(o.total_amount - SUM(oi.quantity * oi.unit_price - oi.discount)) > 0.01
```

**`tests/assert_no_negative_revenue.sql`:**

```sql
-- No revenue should be negative after discounts
SELECT order_id, total_amount
FROM {{ ref('stg_orders') }}
WHERE total_amount < 0
```

**See companion code:**

> `de-fast-track/modules/module-7/solution/dbt/tests/assert_order_total_matches_line_items.sql`
> `de-fast-track/modules/module-7/solution/dbt/tests/assert_no_negative_revenue.sql`

### Custom Generic Tests (Macros)

If you write the same pattern for multiple models, make it a reusable macro.

**`macros/test_row_count_within_range.sql`:**

```sql
{% macro test_row_count_within_range(model, min_count=1, max_count=None) %}

WITH row_count AS (
    SELECT COUNT(*) AS cnt FROM {{ model }}
)
SELECT cnt
FROM row_count
WHERE cnt < {{ min_count }}
{% if max_count is not none %}
   OR cnt > {{ max_count }}
{% endif %}

{% endmacro %}
```

Use it in `schema.yml`:

```yaml
models:
  - name: fact_orders
    tests:
      - row_count_within_range:
          min_count: 1000
          max_count: 5000000
```

**See companion code:**

> `de-fast-track/modules/module-7/solution/dbt/macros/test_row_count_within_range.sql`

### Freshness Tests

dbt has source freshness built in:

```yaml
sources:
  - name: raw
    database: ecommerce
    schema: raw
    tables:
      - name: orders
        loaded_at_field: loaded_at
        freshness:
          warn_after: {count: 12, period: hour}
          error_after: {count: 24, period: hour}
```

```bash
dbt source freshness
```

> **Common Mistake:**
> - Only using generic tests. `unique` and `not_null` are just the baseline. Custom tests for business logic are where the real value is.
> - Not running `dbt test` in CI/CD. Tests should run on every PR and every production deploy.

> **Pro Tip:** Create a `tests/` directory structure that mirrors your models. When a model changes, the associated tests are easy to find and update.

### Checkpoint

1. What's the difference between a dbt generic test and a custom test?
2. In a custom dbt test SQL file, what does it mean when the query returns rows?
3. How would you test that a fact table's foreign key always has a matching dimension record?

---

## 7.5 Data Contracts -- Defining and Enforcing Them

> **TL;DR:** A data contract is a formal agreement between data producers and consumers. It specifies schema, semantics, SLAs, and quality guarantees. Without one, upstream changes silently break your pipeline. Start simple with YAML files in a shared Git repo.

Here's a scenario you'll hit in every data team: the backend team changes a column name. They don't tell you. Your pipeline breaks at 2 AM. You find out at 9 AM when dashboards go red.

Whose fault is it? Neither side's. The fault is that there's no *contract* between the producer and the consumer.

**At your job, this is how it goes down.** The backend team ships a "small refactor" on Friday afternoon. They rename `user_email` to `email_address` in the API response. Your pipeline ingests the data fine -- no errors, because the JSON just has a different key now. But your downstream `dim_customers` table has NULLs in the email column for the entire weekend. Marketing sends a campaign to "Dear NULL" on Monday morning. Nobody's happy.

### What a Data Contract Specifies

A data contract covers:

- **Schema** -- column names, types, nullable or not
- **Semantics** -- what each field means (is `amount` in cents or dollars?)
- **SLAs** -- when data will be available, how fresh it'll be
- **Quality guarantees** -- max null rate, valid value ranges
- **Change management** -- how changes get communicated and versioned

Think of it like a REST API contract. If an API changes its response format without warning, that's a bug. Same principle applies to data.

> **Key Concept: Data Contract**
> A formal, versioned agreement between a data producer and consumer that defines the expected schema, semantics, quality, and delivery SLAs. A contract without enforcement is just documentation.

### Implementing a Basic Contract

**`contracts/raw_orders_contract.yml`:**

```yaml
contract:
  name: raw_orders
  version: "1.0"
  owner: data-engineering
  description: "Raw orders from the ShopFast application database"

  schema:
    fields:
      - name: order_id
        type: integer
        required: true
        unique: true
      - name: customer_id
        type: integer
        required: true
      - name: order_date
        type: timestamp
        required: true
      - name: status
        type: string
        required: true
        allowed_values: [pending, completed, returned, cancelled]
      - name: total_amount
        type: decimal
        required: true
        min_value: 0

  quality:
    freshness:
      field: order_date
      max_age: "48h"
    row_count:
      min: 1
    custom_checks:
      - name: "order_total_positive"
        sql: "SELECT COUNT(*) FROM {table} WHERE total_amount < 0"
        expected: 0

  sla:
    availability: "99.9%"
    update_frequency: "daily"
```

**See companion code:**

> `de-fast-track/modules/module-7/solution/contracts/raw_orders_contract.yml` (complete)
> `de-fast-track/modules/module-7/starter/contracts/raw_orders_contract_starter.yml` (with TODOs)

### Python Contract Validator

This is a production pattern: data contracts as the API between teams. The contract YAML is the interface definition, and the validator is the runtime enforcement.

```python
"""Data contract validator -- validates data against YAML contract specs."""
import yaml
import psycopg2
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


@dataclass
class ContractViolation:
    check_name: str
    severity: str
    message: str
    details: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    contract_name: str
    passed: bool
    violations: list[ContractViolation] = field(default_factory=list)
    checked_at: datetime = field(default_factory=datetime.now)

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


class ContractValidator:
    def __init__(self, connection_string: str):
        self.conn = psycopg2.connect(connection_string)

    def validate(self, contract_path: str, table_name: str) -> ValidationResult:
        contract = self._load_contract(contract_path)
        violations = []
        violations.extend(self._check_schema(contract, table_name))
        if "quality" in contract.get("contract", {}):
            violations.extend(
                self._check_quality(contract["contract"]["quality"], table_name)
            )
        return ValidationResult(
            contract_name=contract["contract"]["name"],
            passed=all(v.severity != "error" for v in violations),
            violations=violations,
        )

    def _load_contract(self, path: str) -> dict:
        with open(path) as f:
            return yaml.safe_load(f)

    def _check_schema(self, contract: dict, table_name: str) -> list[ContractViolation]:
        violations = []
        cur = self.conn.cursor()
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = %s ORDER BY ordinal_position
        """, (table_name,))
        actual = {r[0]: {"type": r[1], "nullable": r[2] == "YES"} for r in cur.fetchall()}

        for field_spec in contract.get("contract", {}).get("schema", {}).get("fields", []):
            name = field_spec["name"]
            if name not in actual:
                violations.append(ContractViolation(
                    f"schema.field_exists.{name}", "error",
                    f"Required field '{name}' not found in table",
                ))
                continue
            if field_spec.get("required"):
                cur.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {name} IS NULL")
                nulls = cur.fetchone()[0]
                if nulls > 0:
                    violations.append(ContractViolation(
                        f"data.not_null.{name}", "error",
                        f"Found {nulls} null values in required field '{name}'",
                        {"null_count": nulls},
                    ))
            if field_spec.get("unique"):
                cur.execute(f"SELECT COUNT(*) - COUNT(DISTINCT {name}) FROM {table_name}")
                dupes = cur.fetchone()[0]
                if dupes > 0:
                    violations.append(ContractViolation(
                        f"data.unique.{name}", "error",
                        f"Found {dupes} duplicate values in unique field '{name}'",
                    ))
        return violations

    def _check_quality(self, quality: dict, table_name: str) -> list[ContractViolation]:
        violations = []
        cur = self.conn.cursor()

        if "row_count" in quality:
            cur.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cur.fetchone()[0]
            min_count = quality["row_count"].get("min", 0)
            if count < min_count:
                violations.append(ContractViolation(
                    "quality.row_count", "error",
                    f"Row count {count} below minimum {min_count}",
                ))

        if "freshness" in quality:
            field_name = quality["freshness"]["field"]
            cur.execute(f"SELECT MAX({field_name}) FROM {table_name}")
            max_date = cur.fetchone()[0]
            if max_date:
                hours = int(quality["freshness"]["max_age"].replace("h", ""))
                if datetime.now() - max_date > timedelta(hours=hours):
                    violations.append(ContractViolation(
                        "quality.freshness", "error",
                        f"Data is stale. Latest record: {max_date}",
                    ))

        for check in quality.get("custom_checks", []):
            cur.execute(check["sql"].replace("{table}", table_name))
            result = cur.fetchone()[0]
            if result != check["expected"]:
                violations.append(ContractViolation(
                    f"quality.custom.{check['name']}", "error",
                    f"Check '{check['name']}' failed: got {result}, expected {check['expected']}",
                ))
        return violations

    def close(self):
        self.conn.close()
```

**Expected output (violation detected):**

```
[nullable] customer_id: 3 null values in non-nullable column
[allowed_values] status: 7 values not in allowed set
Contract violated: 2 issues found
```

**See companion code:**

> `de-fast-track/modules/module-7/solution/quality/contract_validator.py` (complete)
> `de-fast-track/modules/module-7/starter/quality/contract_validator_starter.py` (with TODOs)

> **Pro Tip:** At smaller companies, a YAML contract file in a shared Git repo is often enough. The point isn't fancy tooling -- it's having an explicit agreement that both sides can reference. Big companies like Google, Airbnb, and Netflix all use data contracts internally.

> **Common Mistake:**
> - Making contracts too strict too fast. Start with critical fields and expand.
> - Not versioning contracts. When the schema changes, bump the version and communicate.
> - Having contracts that nobody checks. A contract without enforcement is just documentation.

### Checkpoint

1. What five things does a data contract specify?
2. Why should you version your data contracts?
3. What's the difference between a data contract and a Great Expectations suite?

---

## 7.6 Monitoring, Alerting, and Incident Response

> **TL;DR:** Monitor at three levels: pipeline health, data quality, and business metrics. Alert only on actionable failures (avoid alert fatigue). When bad data gets through, follow a structured incident response: assess scope -> stop the bleeding -> communicate -> root cause -> fix & backfill -> post-mortem.

You've built quality checks. They run every day. Everything's green. Until it's not. And when it's not, you need to know *immediately* -- not when an analyst Slacks you 3 hours later.

### Three Monitoring Layers

1. **Pipeline health** -- Did the DAG run? Did it succeed? How long did it take?
2. **Data quality** -- Did the quality checks pass? What's the trend over time?
3. **Business metrics** -- Are the downstream metrics in expected ranges?

### Pipeline Health Monitoring in Airflow

```python
from airflow import DAG
from airflow.providers.slack.notifications.slack import send_slack_notification
from datetime import datetime, timedelta

default_args = {
    "owner": "data-engineering",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=1),
    "sla": timedelta(hours=2),  # Must complete within 2 hours
    "on_failure_callback": send_slack_notification(
        slack_conn_id="slack_webhook",
        text="DAG `{{ dag.dag_id }}` failed on task `{{ ti.task_id }}`\n"
             "Execution date: {{ ds }}\n"
             "Log: {{ ti.log_url }}",
        channel="#data-alerts",
    ),
    "on_sla_miss_callback": send_slack_notification(
        slack_conn_id="slack_webhook",
        text="SLA MISS: DAG `{{ dag.dag_id }}` didn't complete in time\n"
             "Expected by: {{ sla }}\n"
             "This affects downstream dashboards.",
        channel="#data-alerts",
    ),
}

dag = DAG(
    "ecommerce_pipeline",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
)
```

### Custom Quality Alerting to Slack

```python
import requests


def send_quality_alert(
    webhook_url: str,
    pipeline_name: str,
    check_results: list[dict],
) -> None:
    """Send data quality alert to Slack."""
    failures = [r for r in check_results if not r["success"]]

    if not failures:
        return  # No news is good news

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Data Quality Alert: {pipeline_name}",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{len(failures)} checks failed* out of {len(check_results)} total",
            },
        },
    ]

    for failure in failures[:5]:  # Cap at 5 to avoid spam
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*{failure['check_name']}*\n"
                    f"Column: `{failure.get('column', 'N/A')}`\n"
                    f"Details: {failure['details']}"
                ),
            },
        })

    if len(failures) > 5:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"...and {len(failures) - 5} more failures. Check Data Docs for full report.",
            },
        })

    requests.post(webhook_url, json={"blocks": blocks})
```

### Incident Response Playbook

When bad data gets through -- and it will eventually -- follow this playbook:

**Step 1: Assess Scope** (5 minutes)
- What data is affected? Which tables, which date ranges?
- Who's impacted? Which dashboards, reports, or downstream systems?
- Is the bad data still flowing, or was it a one-time issue?

**Step 2: Stop the Bleeding** (10 minutes)
- Pause the pipeline (Airflow: pause the DAG)
- If bad data is already in the warehouse, mark it -- don't delete it yet

```sql
-- Quarantine bad data (don't delete -- you'll need it for investigation)
ALTER TABLE fact_orders ADD COLUMN IF NOT EXISTS _quarantined BOOLEAN DEFAULT FALSE;

UPDATE fact_orders
SET _quarantined = TRUE
WHERE loaded_at BETWEEN '2026-02-18 00:00:00' AND '2026-02-18 23:59:59'
  AND <condition_that_identifies_bad_data>;
```

**Step 3: Communicate** (immediately)
- Post in #data-alerts with what you know so far
- Be honest: *"We identified a data quality issue. Dashboard X may show incorrect numbers for [date range]. We're investigating."*

**Step 4: Root Cause** (30 min - 2 hours)
- Check upstream sources: Did the source data change?
- Check pipeline logs: Any errors or warnings you missed?
- Check transformations: Did a code change introduce a bug?

**Step 5: Fix and Backfill** (varies)
- Fix the root cause
- Backfill the affected data
- Re-run quality checks to confirm

**Step 6: Post-Mortem** (next day)
- What happened?
- Why didn't our checks catch it?
- What check do we add to prevent this in the future?

> **Common Mistake:**
> - **Alert fatigue.** If you alert on everything, people ignore alerts. Only alert on *actionable* failures.
> - **No runbook.** When it's 2 AM and you're half asleep, you need a checklist, not a thought process.
> - **Deleting bad data** instead of quarantining it. You might need it for the investigation.

### Checkpoint

1. What are the three levels of monitoring for a data pipeline?
2. Why should you quarantine bad data instead of deleting it?
3. What's the purpose of a post-mortem after a data incident?

---

## 7.7 Building a Quality Culture: Shift-Left Testing

This is the production pattern that separates mature data teams from reactive ones: **shift-left testing**. The idea, borrowed from software engineering, is simple: catch problems as early as possible in the pipeline, not at the end.

```
Traditional:  Extract -> Load -> Transform -> [CHECK] -> Serve
Shift-left:   Extract -> [CHECK] -> Load -> [CHECK] -> Transform -> [CHECK] -> Serve
```

At each checkpoint, you have a quality gate. If data fails the gate, it doesn't move forward. Bad data gets quarantined, alerts fire, and the pipeline stops -- instead of silently corrupting your warehouse.

**At your job, this is the difference between:** "We caught the schema change at ingestion, quarantined the bad batch, and alerted the backend team within 15 minutes" vs. "The CEO asked why revenue dropped 90% and we spent 4 hours figuring out what happened."

### The Quality Gate Pattern

Every quality gate asks three questions:
1. **Does the data look like what we expect?** (schema, types, columns)
2. **Is the data reasonable?** (nulls, ranges, volumes, freshness)
3. **Is the data consistent?** (cross-table checks, referential integrity)

If any answer is "no" at severity=error, the pipeline stops. Severity=warning logs and continues.

---

## 7.8 Module 7 Project -- Data Quality Pipeline

> **TL;DR:** Add a comprehensive data quality layer to your Airflow pipeline: contract validation before loading, Great Expectations checks after transformation, Slack alerts on failure, and quarantine for bad data.

### Overview

You're going to add comprehensive data quality checks to your Airflow pipeline from Module 4. When complete, your pipeline will:

1. Validate incoming data against a contract before loading
2. Run Great Expectations checks after each transformation step
3. Alert to Slack (or console) when checks fail
4. Quarantine bad data instead of loading it to production tables

### Project Structure

```
module-7-project/
  dags/
  |   ecommerce_pipeline_with_quality.py
  contracts/
  |   raw_orders_contract.yml
  great_expectations/
  |   great_expectations.yml
  |   expectations/
  |       raw_orders_suite.json
  |       fact_orders_suite.json
  quality/
  |   __init__.py
  |   contract_validator.py
  |   alerts.py
  tests/
  |   test_contract_validator.py
  |   test_quality_checks.py
  docker-compose.yml
  README.md
```

### Step 1: Set Up the Contract

Use the contract YAML from Section 7.5. Customize it for your specific e-commerce schema.

### Step 2: Build the Contract Validator

Take the `validate_contract()` function from Section 7.5 and enhance it with severity levels and structured results:

```python
# quality/contract_validator.py
import yaml
import pandas as pd
from dataclasses import dataclass, asdict
from datetime import datetime
import json


@dataclass
class ContractViolation:
    field: str
    check: str
    details: str
    severity: str = "error"  # "error" or "warning"


@dataclass
class ValidationResult:
    contract_name: str
    contract_version: str
    validated_at: str
    row_count: int
    violations: list[ContractViolation]

    @property
    def passed(self) -> bool:
        return not any(v.severity == "error" for v in self.violations)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, default=str)


def validate_contract(df: pd.DataFrame, contract_path: str) -> ValidationResult:
    """Full contract validation. Returns a ValidationResult."""
    # YOUR IMPLEMENTATION HERE
    # Use the code from Section 7.5 as your starting point
    # Return a ValidationResult instead of a list
    pass
```

### Step 3: Set Up Great Expectations

Create expectation suites for:
- `raw_orders_suite` -- checks on raw ingested data
- `fact_orders_suite` -- checks on transformed fact table

**Minimum expectations per suite:**
- Schema validation (columns exist, correct types)
- Null checks on primary keys and required fields
- Value range checks on numeric columns
- Allowed value checks on categorical columns
- Uniqueness on primary keys
- Row count within expected range

### Step 4: Build the Airflow DAG

```python
# dags/ecommerce_pipeline_with_quality.py
from airflow.decorators import dag, task
from datetime import datetime

@dag(
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["ecommerce", "data-quality"],
)
def ecommerce_pipeline_with_quality():

    @task()
    def extract_orders(**context):
        """Extract orders from source."""
        pass

    @task()
    def validate_contract(**context):
        """Validate raw data against contract BEFORE loading.
        If contract fails, raise exception (pipeline stops)."""
        pass

    @task()
    def load_raw(**context):
        """Load validated data to raw layer."""
        pass

    @task()
    def run_raw_quality_checks(**context):
        """Run Great Expectations on raw data.
        If critical checks fail, raise exception."""
        pass

    @task()
    def transform(**context):
        """Transform raw to fact/dim tables."""
        pass

    @task()
    def run_transformed_quality_checks(**context):
        """Run Great Expectations on transformed data."""
        pass

    @task(trigger_rule="one_failed")
    def quarantine_bad_data(**context):
        """Move bad data to quarantine table instead of deleting."""
        pass

    @task(trigger_rule="all_done")
    def send_quality_report(**context):
        """Send summary of quality results (pass or fail)."""
        pass

    # Define the flow
    raw_data = extract_orders()
    contract_ok = validate_contract()
    loaded = load_raw()
    raw_quality = run_raw_quality_checks()
    transformed = transform()
    final_quality = run_transformed_quality_checks()
    quarantine = quarantine_bad_data()
    report = send_quality_report()

    raw_data >> contract_ok >> loaded >> raw_quality >> transformed >> final_quality
    [raw_quality, final_quality] >> quarantine
    [final_quality, quarantine] >> report

ecommerce_pipeline_with_quality()
```

### Step 5: Write Tests

```python
# tests/test_contract_validator.py
import pytest
import pandas as pd
from quality.contract_validator import validate_contract, ValidationResult


def test_valid_data_passes_contract():
    df = pd.DataFrame({
        "order_id": [1, 2, 3],
        "customer_id": [100, 101, 102],
        "order_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "total_amount": [29.99, 49.99, 19.99],
        "status": ["pending", "shipped", "delivered"],
    })
    result = validate_contract(df, "contracts/raw_orders_contract.yml")
    assert result.passed


def test_null_primary_key_fails():
    df = pd.DataFrame({
        "order_id": [1, None, 3],
        "customer_id": [100, 101, 102],
        "order_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "total_amount": [29.99, 49.99, 19.99],
        "status": ["pending", "shipped", "delivered"],
    })
    result = validate_contract(df, "contracts/raw_orders_contract.yml")
    assert not result.passed


def test_invalid_status_fails():
    df = pd.DataFrame({
        "order_id": [1, 2, 3],
        "customer_id": [100, 101, 102],
        "order_date": pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
        "total_amount": [29.99, 49.99, 19.99],
        "status": ["pending", "shipped", "YOLO"],  # Invalid status
    })
    result = validate_contract(df, "contracts/raw_orders_contract.yml")
    assert not result.passed
    assert any(v.check == "allowed_values" for v in result.violations)
```

**See companion code:**

> `de-fast-track/modules/module-7/solution/tests/test_contract_validator.py`

### Try It Yourself

- Add a test for negative `total_amount` values.
- Add a test for duplicate `order_id` values.
- Add a test that verifies extra columns generate a warning but not an error.

### Expected Output

When you run the DAG successfully:
- All quality checks pass -> green in Airflow, summary report sent
- Bad data detected -> pipeline stops at the quality check step, bad data quarantined, alert sent
- Quality report shows: total checks run, pass/fail per check, trend vs previous run

### Completion Checklist

- [ ] Contract YAML file covers all critical fields
- [ ] Contract validator catches: missing columns, nulls, invalid values, range violations
- [ ] Great Expectations suites for both raw and transformed data
- [ ] Airflow DAG has quality checks at multiple stages
- [ ] Pipeline stops on critical failures (doesn't load bad data)
- [ ] Quarantine mechanism for bad data
- [ ] Alerting function sends notifications on failure
- [ ] At least 5 unit tests for the contract validator
- [ ] README documents the quality checks and how to add new ones

---

## Interview Prep: Data Quality

When they ask "how do you ensure data quality," here's the framework that will set you apart:

**The Layered Approach:**
1. **Data contracts** at the boundary between teams -- schema, semantics, SLAs defined in YAML, validated at ingestion
2. **Schema validation** before data enters the pipeline -- catch drift immediately
3. **Completeness and freshness checks** on raw data -- nulls, staleness, volume anomalies
4. **Business logic tests** on transformed data (dbt tests) -- referential integrity, range checks, uniqueness
5. **Automated quality frameworks** (Great Expectations or Soda) for scalable, config-driven checks
6. **Monitoring and alerting** -- know within minutes, not days, when something breaks
7. **Incident response** -- quarantine, communicate, root cause, backfill, post-mortem

**Key phrases interviewers want to hear:**
- "Shift-left testing" -- catch issues early, not at the end
- "Quality gates" -- data doesn't move forward until it passes checks
- "Data contracts" -- formal agreements between producers and consumers
- "Defense in depth" -- multiple layers of checks, not just one
- "Quarantine, don't delete" -- preserve bad data for investigation

**The story to tell:** "At my previous role, we had a pipeline that loaded orders data daily. Everything looked fine until our CEO's dashboard showed a 90% revenue drop. Turned out a source API changed its schema silently. After that incident, I implemented data contracts with the backend team, added schema validation at ingestion, and built automated quality checks with Great Expectations. We went from finding issues days later to catching them within minutes."

---

## What's Next

With data quality and testing covered, Module 8 shifts to cloud infrastructure for data engineers. You'll learn the AWS services that matter for DE work (S3, Redshift, Athena, Glue, IAM), how to deploy your pipelines to the cloud, and the patterns that scale.

---

*End of Module 7*
