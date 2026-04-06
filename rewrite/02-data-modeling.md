# Module 2: SQL for Data Engineers

SQL is the lingua franca of data engineering. Not Python, not Spark, not Terraform -- SQL. Every data warehouse, every transformation layer, every quality check runs on SQL at the core. This module takes you from "I can write a SELECT" to "I can build a production incremental ETL pipeline in pure SQL." These are the exact patterns you will write every single day on the job.

> **Why this module matters:** In data engineering interviews, SQL is the great equalizer. You can talk about Spark architecture and Kubernetes orchestration all day long, but if you cannot write a window function on a whiteboard, you will not get the offer. Window functions and CTEs are the number one SQL skill gap interviewers test for. Master this module and you close that gap permanently.

---

## 2.1 CTEs and Recursive CTEs

### Common Table Expressions: Named Steps for Readable SQL

A CTE (Common Table Expression) is a named temporary result set that exists only for the duration of a single query. It replaces nested subqueries with readable, named steps. You will write CTEs like this every day -- every dbt model is basically a chain of CTEs.

Here is a simple CTE that replaces a nested subquery:

```sql
-- WITHOUT CTEs: nested subqueries become unreadable fast
SELECT *
FROM (
    SELECT customer_id, SUM(amount) AS total
    FROM (
        SELECT * FROM orders WHERE status = 'completed'
    ) completed_orders
    GROUP BY customer_id
) customer_totals
WHERE total > 1000;

-- WITH CTEs: each step has a name and a purpose
WITH completed_orders AS (
    SELECT *
    FROM orders
    WHERE status = 'completed'
),
customer_totals AS (
    SELECT customer_id, SUM(amount) AS total
    FROM completed_orders
    GROUP BY customer_id
)
SELECT *
FROM customer_totals
WHERE total > 1000;
```

The second version does the exact same thing, but six months from now when you or a teammate revisits this code, every step is self-documenting.

### The Pipeline Pattern: staging -> dedup -> enrich -> validate -> output

In production data engineering, CTEs follow a standard pipeline pattern. This is the skeleton of every serious transformation you will write:

```sql
WITH staging AS (
    -- Raw data from source, minimal transformation
    SELECT
        id,
        name,
        email,
        city,
        state,
        updated_at,
        ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC) AS rn
    FROM raw_customers
),
deduped AS (
    -- Remove duplicates: keep only the most recent row per customer
    SELECT * FROM staging WHERE rn = 1
),
enriched AS (
    -- Add business logic: segment classification, derived fields
    SELECT
        d.*,
        CASE
            WHEN state IN ('CA','NY','TX') THEN 'Tier 1'
            WHEN state IN ('FL','IL','PA') THEN 'Tier 2'
            ELSE 'Tier 3'
        END AS market_tier,
        CURRENT_DATE AS load_date
    FROM deduped d
),
validated AS (
    -- Filter out bad data before loading
    SELECT *
    FROM enriched
    WHERE email IS NOT NULL
      AND email LIKE '%@%.%'
      AND name IS NOT NULL
)
SELECT * FROM validated;
```

**When you will use this at work:** Every dbt model you write. Every staging-to-warehouse transformation. Every data pipeline that reads from a source, cleans it, enriches it, and loads it. The staging-dedup-enrich-validate-output pattern is the backbone of data transformation. When you open a dbt project at a new company on your first day, you will see exactly this structure in every model.

### Recursive CTEs: Hierarchies in SQL

Recursive CTEs solve the class of problems where data references itself -- org charts (who reports to whom), category trees (Electronics > Phones > Smartphones), bill-of-materials (a car contains an engine, which contains pistons...).

```sql
-- Org chart: find all reports under a given manager
WITH RECURSIVE org_tree AS (
    -- Anchor: start with the top-level manager
    SELECT
        employee_id,
        name,
        manager_id,
        1 AS depth
    FROM employees
    WHERE manager_id IS NULL  -- CEO / top of tree

    UNION ALL

    -- Recursive step: find all direct reports of people already in our result
    SELECT
        e.employee_id,
        e.name,
        e.manager_id,
        ot.depth + 1
    FROM employees e
    JOIN org_tree ot ON e.manager_id = ot.employee_id
    WHERE ot.depth < 10  -- ALWAYS add a depth limit
)
SELECT * FROM org_tree ORDER BY depth, name;
```

**Always add a depth limit.** Without one, a single circular reference in your data (employee A reports to B, B reports to A) will cause an infinite loop that consumes memory until Postgres kills the query -- or your DBA kills you. In production, set the depth limit to the maximum reasonable level for your hierarchy plus a safety margin. If your org chart is never more than 8 levels deep, set the limit to 15.

Another common use -- exploding category trees for a product catalog:

```sql
-- Category breadcrumb: Electronics > Audio > Headphones
WITH RECURSIVE category_path AS (
    SELECT
        category_id,
        name,
        parent_id,
        name AS full_path,
        1 AS depth
    FROM categories
    WHERE parent_id IS NULL  -- root categories

    UNION ALL

    SELECT
        c.category_id,
        c.name,
        c.parent_id,
        cp.full_path || ' > ' || c.name,
        cp.depth + 1
    FROM categories c
    JOIN category_path cp ON c.parent_id = cp.category_id
    WHERE cp.depth < 10
)
SELECT * FROM category_path ORDER BY full_path;
```

**When you will use this at work:** E-commerce category trees, organizational reporting structures, permission hierarchies (role A inherits from role B), network topology (which switches connect to which routers). Any time your data has a parent-child relationship, recursive CTEs are the answer.

> **Key Takeaway:** CTEs turn unreadable nested SQL into a pipeline of named steps. The staging-dedup-enrich-validate-output pattern is the universal skeleton for data transformations. Recursive CTEs handle hierarchies, but always add a depth limit to prevent infinite loops.

---

## 2.2 Window Functions Deep Dive

Window functions are the most powerful feature in SQL and the single biggest skill gap in data engineering interviews. If you can write window functions fluently, you are ahead of 80% of candidates.

A window function performs a calculation across a set of rows that are *related to the current row* -- without collapsing those rows into a single output like GROUP BY does. Think of it as: GROUP BY gives you one row per group, but a window function gives you one result per row with awareness of the group.

### Anatomy of a Window Function

```sql
SELECT
    employee_id,
    department,
    salary,
    -- This is a window function
    AVG(salary) OVER (
        PARTITION BY department    -- which rows form the "window"
        ORDER BY hire_date         -- how they are ordered within the window
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW  -- the "frame"
    ) AS running_avg_salary
FROM employees;
```

The three parts:
1. **PARTITION BY** -- Divides rows into groups (like GROUP BY, but without collapsing). Each partition is processed independently.
2. **ORDER BY** -- Defines the order of rows within each partition. Required for ranking functions and running aggregations.
3. **Frame clause** (ROWS BETWEEN...) -- Defines exactly which rows relative to the current row are included in the calculation. This is the part most people get wrong.

### ROW_NUMBER for Dedup: THE Dedup Technique

This is the single most important SQL pattern in data engineering. When source systems send you duplicate records, CDC streams replay events, or batch loads overlap, you need to deduplicate. ROW_NUMBER is how you do it:

```sql
-- THE dedup pattern: keep only the most recent record per customer
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY updated_at DESC
        ) AS rn
    FROM raw_customers
)
SELECT * FROM ranked WHERE rn = 1;
```

**How it works:** PARTITION BY customer_id groups all rows for the same customer together. ORDER BY updated_at DESC sorts them newest-first within each group. ROW_NUMBER() assigns 1 to the newest, 2 to the second-newest, and so on. Filtering to rn = 1 keeps only the latest version of each customer.

**Why ROW_NUMBER and not DISTINCT or GROUP BY?** DISTINCT removes exact duplicates but cannot pick "the most recent" among near-duplicates. GROUP BY collapses rows so you lose the non-aggregated columns. ROW_NUMBER gives you full control: keep the latest by timestamp, the highest-priority by status, or the first-arrived by ingestion time -- whatever your business logic requires.

**When you will use this at work:** Every. Single. Day. CDC streams often replay events, leaving you with multiple versions of the same record. Batch loads can overlap, giving you two copies of yesterday's data. Source systems have bugs that create true duplicates. The ROW_NUMBER dedup pattern is the universal fix.

### RANK vs DENSE_RANK vs ROW_NUMBER

These three ranking functions differ only in how they handle ties:

```sql
SELECT
    student_name,
    score,
    ROW_NUMBER() OVER (ORDER BY score DESC) AS row_num,    -- No ties: 1,2,3,4,5
    RANK()       OVER (ORDER BY score DESC) AS rank_val,    -- Ties skip: 1,2,2,4,5
    DENSE_RANK() OVER (ORDER BY score DESC) AS dense_val    -- Ties don't skip: 1,2,2,3,4
FROM exam_scores;
```

| student | score | ROW_NUMBER | RANK | DENSE_RANK |
|---------|-------|-----------|------|------------|
| Alice   | 95    | 1         | 1    | 1          |
| Bob     | 90    | 2         | 2    | 2          |
| Carol   | 90    | 3         | 2    | 2          |
| David   | 85    | 4         | 4    | 3          |
| Eve     | 80    | 5         | 5    | 4          |

- **ROW_NUMBER**: Always unique. Use for dedup (you want exactly one row per group, no ties).
- **RANK**: Gaps after ties. Use when gaps matter ("3rd place, no 2nd place" like Olympic medals).
- **DENSE_RANK**: No gaps. Use for "top N categories" where you want exactly N distinct values.

### LAG/LEAD: Time-Series Analysis

LAG looks at the previous row, LEAD looks at the next row. These are indispensable for time-series analysis -- month-over-month growth, session boundary detection, and change detection.

```sql
-- Month-over-month revenue growth
WITH monthly_revenue AS (
    SELECT
        DATE_TRUNC('month', order_date) AS month,
        SUM(revenue) AS revenue
    FROM fact_orders f
    JOIN dim_date d ON f.date_key = d.date_key
    GROUP BY DATE_TRUNC('month', order_date)
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
    ROUND(
        (revenue - LAG(revenue) OVER (ORDER BY month))
        / LAG(revenue) OVER (ORDER BY month) * 100, 1
    ) AS growth_pct
FROM monthly_revenue
ORDER BY month;
```

**When you will use this at work:** Every executive dashboard has a "vs. last month" or "vs. last year" metric. LAG computes it in one line. You will also use it for detecting anomalies -- if today's row count is 50% lower than yesterday's, something is broken.

### Running Aggregations: Cumulative Sum and Moving Average

```sql
-- Cumulative revenue: "how much total revenue have we earned through this date"
SELECT
    order_date,
    daily_revenue,
    SUM(daily_revenue) OVER (
        ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_revenue_summary;

-- 7-day moving average: smooths out daily noise
SELECT
    order_date,
    daily_revenue,
    AVG(daily_revenue) OVER (
        ORDER BY order_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS moving_avg_7d
FROM daily_revenue_summary;
```

**Understanding window frames -- the part most people get wrong:**

- `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` -- All rows from the start of the partition up to the current row. This is for cumulative/running totals.
- `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` -- The current row plus the 6 before it (7 total). This is for moving averages.
- `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` -- The entire partition. Same as no frame at all.

The critical gotcha: if you use ORDER BY in a window without specifying a frame, Postgres defaults to `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. RANGE and ROWS behave differently with ties. ROWS is almost always what you want -- it is deterministic and row-based. Use ROWS explicitly to avoid surprises.

### FIRST_VALUE / LAST_VALUE

```sql
-- For each order, show the first and most recent order date per customer
SELECT
    customer_id,
    order_date,
    order_id,
    FIRST_VALUE(order_date) OVER (
        PARTITION BY customer_id ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS first_order_date,
    LAST_VALUE(order_date) OVER (
        PARTITION BY customer_id ORDER BY order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS last_order_date
FROM orders;
```

**Critical:** LAST_VALUE requires `ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING`. Without it, the default frame ends at the current row, so LAST_VALUE just returns the current row's value -- completely useless. This is one of the most common window function bugs.

### The WINDOW Clause: DRY Principle for Windows

When you reuse the same window specification, define it once:

```sql
SELECT
    customer_id,
    order_date,
    revenue,
    SUM(revenue)   OVER w AS cumulative_revenue,
    AVG(revenue)   OVER w AS running_avg,
    COUNT(*)       OVER w AS order_number
FROM orders
WINDOW w AS (PARTITION BY customer_id ORDER BY order_date
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
ORDER BY customer_id, order_date;
```

### The Sessionization Pattern

Sessionization groups a stream of events (clickstream, app events, IoT readings) into logical sessions. This is a classic interview question and a real production need.

The logic: if more than 30 minutes pass between two consecutive events from the same user, start a new session.

```sql
WITH events_with_gap AS (
    SELECT
        user_id,
        event_time,
        event_type,
        -- Time since the previous event for this user
        EXTRACT(EPOCH FROM (
            event_time - LAG(event_time) OVER (PARTITION BY user_id ORDER BY event_time)
        )) / 60.0 AS minutes_since_last
    FROM clickstream_events
),
session_boundaries AS (
    SELECT
        *,
        -- Flag: is this the start of a new session?
        CASE
            WHEN minutes_since_last IS NULL THEN 1  -- first event ever
            WHEN minutes_since_last > 30 THEN 1     -- gap > 30 min
            ELSE 0
        END AS is_new_session
    FROM events_with_gap
),
sessionized AS (
    SELECT
        *,
        -- Running sum of session boundaries = session ID
        SUM(is_new_session) OVER (
            PARTITION BY user_id ORDER BY event_time
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS session_id
    FROM session_boundaries
)
SELECT
    user_id,
    session_id,
    MIN(event_time) AS session_start,
    MAX(event_time) AS session_end,
    COUNT(*) AS events_in_session,
    EXTRACT(EPOCH FROM (MAX(event_time) - MIN(event_time))) / 60.0 AS session_duration_min
FROM sessionized
GROUP BY user_id, session_id;
```

**How it works, step by step:**
1. LAG computes the gap between consecutive events per user.
2. Any gap over 30 minutes (or the first event) is flagged as a session boundary.
3. A running SUM of boundary flags creates a monotonically increasing session ID.
4. GROUP BY session_id gives you session-level metrics.

**When you will use this at work:** Product analytics teams need session data for every analysis -- average session duration, sessions per user, conversion funnels within sessions. Google Analytics, Amplitude, and Mixpanel all do exactly this internally. If your company builds its own product analytics on a warehouse, you will write this pattern.

> **Key Takeaway:** Window functions are the #1 SQL skill gap in interviews. ROW_NUMBER is THE dedup technique. LAG/LEAD handle time-series comparison. Running SUM handles cumulative metrics. Always specify your window frame explicitly. The sessionization pattern is a classic interview question that combines LAG, CASE, and running SUM.

---

## 2.3 MERGE/UPSERT Patterns

In real data pipelines, you rarely load data into empty tables. Data arrives continuously -- new records appear, existing records change, sometimes records need to be deleted. You need SQL patterns that handle "insert if new, update if changed" -- an upsert.

### INSERT ON CONFLICT: Postgres UPSERT (SCD Type 1)

Postgres provides `INSERT ... ON CONFLICT ... DO UPDATE` as its upsert mechanism. This is the most common pattern for SCD Type 1 (overwrite) dimensions:

```sql
-- SCD Type 1: if the customer exists, overwrite with new values
-- If they don't exist, insert a new row
INSERT INTO dim_customer (customer_id, name, email, city, state, segment)
VALUES (1, 'Alice Johnson', 'alice@newjob.com', 'Boston', 'MA', 'Enterprise')
ON CONFLICT (customer_id) DO UPDATE SET
    name    = EXCLUDED.name,
    email   = EXCLUDED.email,
    city    = EXCLUDED.city,
    state   = EXCLUDED.state,
    segment = EXCLUDED.segment;
```

`EXCLUDED` is a special reference to the row that was proposed for insertion but conflicted. It is the "incoming" row. This pattern is atomic -- no race condition between checking existence and inserting/updating.

**Bulk upsert from a staging table:**

```sql
-- Upsert all customers from staging into dimension
INSERT INTO dim_customer (customer_id, name, email, city, state, segment)
SELECT id, name, email, city, state, segment
FROM stg_customers
ON CONFLICT (customer_id) DO UPDATE SET
    name    = EXCLUDED.name,
    email   = EXCLUDED.email,
    city    = EXCLUDED.city,
    state   = EXCLUDED.state,
    segment = EXCLUDED.segment;
```

**When you will use this at work:** Any dimension where you do not need to track history. Lookup tables, reference data, configuration tables. "The customer changed their email -- just overwrite the old one." This is the default for Type 1 slowly changing dimensions.

### SCD Type 2 Incremental Load: The Full Pattern

SCD Type 2 is harder. When a tracked attribute changes, you do not overwrite -- you expire the old row and insert a new one, preserving full history. This is a multi-step process:

**Step 1: Find what changed and expire the old rows**

```sql
-- Expire current rows where tracked attributes changed
UPDATE dim_customer dc
SET expiry_date = src.updated_at::date - 1,
    is_current = FALSE
FROM src_customers src
WHERE dc.customer_id = src.id
  AND dc.is_current = TRUE
  AND src.updated_at > '2025-01-10'  -- since last load
  AND (dc.city != src.city
       OR dc.state != src.state
       OR dc.segment != src.segment);
```

**Step 2: Insert new current rows for changed records AND brand new records**

```sql
INSERT INTO dim_customer (customer_id, name, email, city, state, country,
                          segment, created_date, effective_date)
SELECT src.id, src.name, src.email, src.city, src.state, 'US',
       src.segment, src.created_at::date, src.updated_at::date
FROM src_customers src
WHERE src.updated_at > '2025-01-10'
  AND (
    -- Changed tracked attributes (we just expired the old row)
    EXISTS (
        SELECT 1 FROM dim_customer dc
        WHERE dc.customer_id = src.id AND dc.is_current = FALSE
          AND dc.expiry_date = src.updated_at::date - 1
    )
    -- Or brand new customer (no row exists at all)
    OR NOT EXISTS (
        SELECT 1 FROM dim_customer dc WHERE dc.customer_id = src.id
    )
  );
```

**Step 3: Type 1 update for non-tracked attributes**

Some attributes do not warrant history tracking -- email addresses, phone numbers. For these, just overwrite (Type 1) even within an SCD Type 2 dimension:

```sql
-- Type 1 update for email (no need to track email history)
UPDATE dim_customer dc
SET email = src.email
FROM src_customers src
WHERE dc.customer_id = src.id
  AND dc.is_current = TRUE
  AND dc.email != src.email;
```

**Production scenario: Your Airflow DAG runs this incremental load nightly.** When customer Alice Johnson moves from New York to Boston, here is exactly what happens in the SCD Type 2 process:

1. The source system updates `src_customers` row for Alice: city changes from 'New York' to 'Boston', `updated_at` becomes '2025-01-11'.
2. Step 1 finds Alice's current row in `dim_customer` where city='New York'. It sets `expiry_date = '2025-01-10'` and `is_current = FALSE`.
3. Step 2 inserts a brand new row for Alice with city='Boston', `effective_date = '2025-01-11'`, `expiry_date = '9999-12-31'`, `is_current = TRUE`.
4. Now Alice has TWO rows in `dim_customer` -- the historical row (New York, effective 2024-06-15 to 2025-01-10) and the current row (Boston, effective 2025-01-11 to 9999-12-31).
5. When you join `fact_orders` to `dim_customer` for Alice's old orders, the join on `is_current = TRUE` gives you Boston. But if you need to know where she lived when she placed that January 5th order, you join on `order_date BETWEEN effective_date AND expiry_date` and you get New York. That is the power of SCD Type 2.

### MERGE: The SQL Standard (Postgres 15+)

MERGE arrived in Postgres 15 and is the SQL standard way to do conditional insert/update/delete in a single statement:

```sql
-- MERGE: one statement handles insert, update, and delete
MERGE INTO dim_product AS target
USING stg_products AS source
ON target.product_id = source.product_id AND target.is_current = TRUE
WHEN MATCHED AND (target.category != source.category
                  OR target.unit_price != source.unit_price) THEN
    UPDATE SET
        expiry_date = CURRENT_DATE - 1,
        is_current = FALSE
WHEN NOT MATCHED THEN
    INSERT (product_id, product_name, category, subcategory,
            brand, unit_cost, unit_price, effective_date)
    VALUES (source.product_id, source.product_name, source.category,
            source.subcategory, source.brand, source.unit_cost,
            source.unit_price, CURRENT_DATE);
```

MERGE is elegant but has limitations -- the SCD Type 2 pattern still requires multiple statements because you need to both expire the old row and insert a new one, and MERGE cannot insert *and* update for the same matched row. In practice, the UPDATE/INSERT two-step pattern from above remains the standard approach for SCD Type 2.

**When you will use this at work:** MERGE is great for simple upserts (insert-or-update). For SCD Type 2, you will use the multi-step UPDATE + INSERT pattern. Both are bread and butter in any ETL pipeline that loads dimensional models.

> **Key Takeaway:** INSERT ON CONFLICT handles Type 1 (overwrite) upserts atomically. SCD Type 2 requires a multi-step process: find changes, expire old rows, insert new rows. MERGE is the SQL standard but cannot fully handle SCD Type 2 in a single statement.

---

## 2.4 Surrogate Keys and SCD SQL Mechanics

### Why Surrogate Keys?

A surrogate key is a meaningless auto-generated identifier assigned by the warehouse, as opposed to the natural/business key from the source system. In our schema, `customer_key` (SERIAL) is the surrogate key, while `customer_id` is the natural key from the source.

Why not just use the natural key? Because SCD Type 2 creates multiple rows for the same customer. Customer Alice (customer_id = 1) has two rows -- one for her New York era and one for her Boston era. If the fact table joined on `customer_id`, it could not distinguish which Alice row to use. The surrogate `customer_key` is unique per row, so the fact table can point to exactly the right version.

### Surrogate Key Generation Strategies

**SERIAL / IDENTITY (auto-increment):**

```sql
CREATE TABLE dim_customer (
    customer_key SERIAL PRIMARY KEY,  -- auto-increment: 1, 2, 3, ...
    customer_id  INT NOT NULL,        -- natural key from source
    ...
);

-- Or the SQL-standard equivalent:
CREATE TABLE dim_customer (
    customer_key INT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  INT NOT NULL,
    ...
);
```

Simple, fast, database-managed. The downside: not portable across databases and not deterministic (reloading data produces different keys).

**Hash-based keys:**

```sql
-- Deterministic: same input always produces the same key
SELECT MD5(customer_id::text || '|' || effective_date::text) AS customer_key;
```

Deterministic and portable. The same source record always gets the same surrogate key regardless of load order. dbt uses this approach (via `dbt_utils.generate_surrogate_key`). The downside: hash collisions (astronomically unlikely but theoretically possible with MD5), and less human-readable.

**UUID:**

```sql
SELECT gen_random_uuid() AS customer_key;
-- Output: 'a81bc81b-dead-4e5d-abff-90865d1e13b1'
```

Globally unique and no collisions. But UUIDs are large (16 bytes vs 4 for INT), bad for index performance, and completely unreadable when debugging. Use them when you need globally unique identifiers across distributed systems, not for warehouse surrogate keys.

**When you will use this at work:** SERIAL for simple warehouses. Hash-based keys for dbt projects (idempotent loads, deterministic keys). UUID when you absolutely need global uniqueness. For the module project, we use SERIAL because it is simple and fits the single-database model.

### IS DISTINCT FROM: NULL-Safe Comparison

Standard SQL comparison with `!=` returns NULL when either side is NULL. That means `NULL != 'Boston'` is NULL (not TRUE), and your change detection silently misses records where old or new values are NULL.

```sql
-- BROKEN: misses changes involving NULLs
WHERE dc.city != src.city  -- NULL != 'Boston' is NULL, not TRUE

-- FIXED: IS DISTINCT FROM treats NULL like a value
WHERE dc.city IS DISTINCT FROM src.city  -- NULL IS DISTINCT FROM 'Boston' is TRUE
```

`IS DISTINCT FROM` treats NULL as a regular value: NULL IS DISTINCT FROM NULL is FALSE, NULL IS DISTINCT FROM 'anything' is TRUE. Use it everywhere in change detection logic. Missing this is a silent data quality bug that can go undetected for months.

### Complete SCD Type 2 Stored Procedure

In production, the SCD Type 2 logic lives in a stored procedure that your scheduler (Airflow, dbt, cron) calls:

```sql
CREATE OR REPLACE PROCEDURE load_dim_customer(p_last_load_ts TIMESTAMP)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Step 1: Expire changed rows
    UPDATE dim_customer dc
    SET expiry_date = src.updated_at::date - 1,
        is_current = FALSE
    FROM src_customers src
    WHERE dc.customer_id = src.id
      AND dc.is_current = TRUE
      AND src.updated_at > p_last_load_ts
      AND (dc.city IS DISTINCT FROM src.city
           OR dc.state IS DISTINCT FROM src.state
           OR dc.segment IS DISTINCT FROM src.segment);

    -- Step 2: Insert new current rows for changed + new
    INSERT INTO dim_customer (customer_id, name, email, city, state, country,
                              segment, created_date, effective_date)
    SELECT src.id, src.name, src.email, src.city, src.state, 'US',
           src.segment, src.created_at::date, src.updated_at::date
    FROM src_customers src
    WHERE src.updated_at > p_last_load_ts
      AND (
        EXISTS (
            SELECT 1 FROM dim_customer dc
            WHERE dc.customer_id = src.id AND dc.is_current = FALSE
              AND dc.expiry_date = src.updated_at::date - 1
        )
        OR NOT EXISTS (
            SELECT 1 FROM dim_customer dc WHERE dc.customer_id = src.id
        )
      );

    -- Step 3: Type 1 update for non-tracked attributes
    UPDATE dim_customer dc
    SET email = src.email
    FROM src_customers src
    WHERE dc.customer_id = src.id
      AND dc.is_current = TRUE
      AND dc.email IS DISTINCT FROM src.email;
END;
$$;

-- Called by Airflow:
CALL load_dim_customer('2025-01-10 00:00:00');
```

> **Key Takeaway:** Surrogate keys enable SCD Type 2 by giving each version of a dimension record a unique identifier. IS DISTINCT FROM is essential for NULL-safe change detection. Wrap the SCD logic in a stored procedure so your scheduler can call it with the last load timestamp.

---

## 2.5 Performance

You can write the most elegant SQL in the world, but if it takes 45 minutes to run on a nightly schedule with a 30-minute window, it is useless. Performance tuning is not optional -- it is a core data engineering skill.

### EXPLAIN ANALYZE: See What the Database Actually Does

EXPLAIN ANALYZE runs the query and shows the actual execution plan with real timings:

```sql
EXPLAIN ANALYZE
SELECT dc.name, SUM(f.revenue)
FROM fact_orders f
JOIN dim_customer dc ON f.customer_key = dc.customer_key
WHERE dc.is_current = TRUE
GROUP BY dc.name;
```

Output (simplified):

```
HashAggregate (actual time=12.3..12.5 rows=10 loops=1)
  -> Hash Join (actual time=0.08..11.2 rows=15 loops=1)
       Hash Cond: (f.customer_key = dc.customer_key)
       -> Seq Scan on fact_orders f (actual time=0.01..5.3 rows=20 loops=1)
       -> Hash (actual time=0.05..0.05 rows=10 loops=1)
            -> Seq Scan on dim_customer dc (actual time=0.01..0.03 rows=10 loops=1)
                 Filter: is_current
Planning Time: 0.3 ms
Execution Time: 12.8 ms
```

What to look for:
- **Seq Scan** on large tables: a full table scan. Fine for small tables, deadly for millions of rows. You need an index.
- **actual time vs estimated rows**: if the planner thinks there are 100 rows but there are 10 million, statistics are stale. Run `ANALYZE table_name;` to refresh.
- **Nested Loop with high loops count**: If the inner side runs millions of times, the join strategy is wrong. Usually means a missing index.

### Indexing: The Biggest Performance Lever

Indexes are the difference between a query scanning 50 million rows and one that reads exactly the 200 rows it needs.

**Composite index (multi-column):**

```sql
-- This index covers the most common fact table join pattern
CREATE INDEX idx_fact_orders_date ON fact_orders(date_key);
CREATE INDEX idx_fact_orders_customer ON fact_orders(customer_key);
CREATE INDEX idx_fact_orders_product ON fact_orders(product_key);
```

**Partial index -- the secret weapon:**

```sql
-- Only index current dimension rows (is_current = TRUE)
-- This index is tiny compared to indexing the whole table
CREATE INDEX idx_dim_customer_current
ON dim_customer(customer_id)
WHERE is_current = TRUE;

CREATE INDEX idx_dim_product_current
ON dim_product(product_id)
WHERE is_current = TRUE;
```

**Production story:** I once saw a query go from 45 minutes to 2 seconds just by adding a partial index. The dimension table had 50 million historical rows but only 2 million current rows. Every SCD Type 2 join was filtering on `is_current = TRUE`, but without the partial index, Postgres was scanning all 50 million rows to find the 2 million current ones. A partial index `WHERE is_current = TRUE` reduced the index size by 96% and turned sequential scans into instant index lookups.

**Composite index for common filter patterns:**

```sql
-- If you frequently query by customer_id and is_current together
CREATE INDEX idx_dim_customer_lookup
ON dim_customer(customer_id, is_current)
WHERE is_current = TRUE;
```

Column order in composite indexes matters. The left-most column is the primary filter. Put the most selective column first.

### Table Partitioning by Date

For fact tables that grow continuously, partitioning by date is essential. Instead of one massive table, you split it into smaller pieces by time period:

```sql
-- Create a partitioned fact table
CREATE TABLE fact_orders (
    order_key    SERIAL,
    order_id     INT NOT NULL,
    customer_key INT NOT NULL,
    product_key  INT NOT NULL,
    date_key     INT NOT NULL,
    quantity     INT NOT NULL,
    unit_price   NUMERIC(10,2) NOT NULL,
    revenue      NUMERIC(12,2) NOT NULL,
    order_status VARCHAR(20)
) PARTITION BY RANGE (date_key);

-- Create partitions for each month
CREATE TABLE fact_orders_2025_01 PARTITION OF fact_orders
    FOR VALUES FROM (20250101) TO (20250201);
CREATE TABLE fact_orders_2025_02 PARTITION OF fact_orders
    FOR VALUES FROM (20250201) TO (20250301);
-- ... and so on
```

**Why partition?** When a query filters on `WHERE date_key BETWEEN 20250101 AND 20250131`, Postgres only scans the January partition and completely ignores the other 11 months. This is called partition pruning and it can reduce I/O by 90%+.

Partitioning also makes maintenance easier:
- Drop an old partition instantly instead of DELETE-ing millions of rows.
- VACUUM and ANALYZE run faster on smaller partitions.
- Backfilling a specific month means replacing one partition, not scanning the entire table.

**When you will use this at work:** Every fact table over ~100 million rows should be partitioned. Most data warehouses partition by date because nearly every query has a date filter. Some also partition by a high-cardinality dimension (customer region, product category) if queries always filter on it.

> **Key Takeaway:** EXPLAIN ANALYZE shows you what is actually slow. Indexes -- especially partial indexes on `is_current = TRUE` -- are the biggest performance lever. Partition large fact tables by date so queries only scan the time range they need.

---

## 2.6 SQL for Data Quality

Data quality checks are not optional nice-to-haves. They are production infrastructure. Every pipeline should include automated quality checks that run after every load. When they fail, you catch the problem before your CFO sees wrong revenue numbers on a dashboard.

### The Six Essential Checks

**1. Completeness -- Are required fields populated?**

```sql
-- Check for NULL values in columns that should never be NULL
SELECT
    'NULL customer names' AS check_name,
    COUNT(*) AS violations
FROM dim_customer
WHERE name IS NULL AND is_current = TRUE;
```

**When you will use this at work:** Source systems change. A developer removes a NOT NULL constraint, an API starts sending empty strings, a CSV import maps columns wrong. Completeness checks catch it on the first load.

**2. Freshness -- Is the data up to date?**

```sql
-- Check that the most recent data is from today (or yesterday for nightly loads)
SELECT
    'Stale data' AS check_name,
    MAX(calendar_date) AS latest_date,
    CURRENT_DATE - MAX(calendar_date) AS days_behind,
    CASE
        WHEN CURRENT_DATE - MAX(calendar_date) > 1 THEN 'FAIL'
        ELSE 'PASS'
    END AS status
FROM fact_orders f
JOIN dim_date d ON f.date_key = d.date_key;
```

**When you will use this at work:** Your Airflow DAG ran, completed "successfully," but actually loaded zero rows because the source table was empty. Without a freshness check, nobody notices for days.

**3. Uniqueness -- Are there duplicate dimension records?**

```sql
-- No customer_id should have more than one current row
SELECT 'Duplicate current customers' AS check_name,
       COUNT(*) AS violations
FROM (
    SELECT customer_id, COUNT(*) AS cnt
    FROM dim_customer WHERE is_current = TRUE
    GROUP BY customer_id HAVING COUNT(*) > 1
) dupes
UNION ALL
SELECT 'Duplicate current products',
       COUNT(*)
FROM (
    SELECT product_id, COUNT(*) AS cnt
    FROM dim_product WHERE is_current = TRUE
    GROUP BY product_id HAVING COUNT(*) > 1
) dupes;
```

**When you will use this at work:** The SCD Type 2 logic has a bug, or two pipeline runs overlap, and now customer Alice has two current rows. Every downstream join doubles her revenue. This check catches it immediately.

**4. Volume Anomaly Detection (Z-Score)**

```sql
-- Alert if today's load volume is statistically unusual
WITH daily_counts AS (
    SELECT
        d.calendar_date,
        COUNT(*) AS row_count
    FROM fact_orders f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE d.calendar_date > CURRENT_DATE - INTERVAL '30 days'
    GROUP BY d.calendar_date
),
stats AS (
    SELECT
        AVG(row_count) AS avg_count,
        STDDEV(row_count) AS stddev_count
    FROM daily_counts
)
SELECT
    dc.calendar_date,
    dc.row_count,
    ROUND((dc.row_count - s.avg_count) / NULLIF(s.stddev_count, 0), 2) AS z_score,
    CASE
        WHEN ABS((dc.row_count - s.avg_count) / NULLIF(s.stddev_count, 0)) > 2 THEN 'ANOMALY'
        ELSE 'NORMAL'
    END AS status
FROM daily_counts dc
CROSS JOIN stats s
ORDER BY dc.calendar_date DESC
LIMIT 1;
```

A z-score above 2 or below -2 means today's volume is more than 2 standard deviations from the 30-day average. That is unusual enough to warrant investigation. Maybe a source system went down (too few rows) or replayed data (too many rows).

**When you will use this at work:** This catches the failures that do not produce errors. The pipeline completes successfully, but loads 10 rows instead of the usual 10,000. Without a volume check, you do not notice until someone complains about a blank dashboard.

**5. Referential Integrity -- Do all foreign keys resolve?**

```sql
-- Orphaned fact records: fact rows pointing to non-existent dimension keys
SELECT 'Orphaned customer keys' AS check_name,
       COUNT(*) AS violations
FROM fact_orders f
LEFT JOIN dim_customer dc ON f.customer_key = dc.customer_key
WHERE dc.customer_key IS NULL
UNION ALL
SELECT 'Orphaned product keys',
       COUNT(*)
FROM fact_orders f
LEFT JOIN dim_product dp ON f.product_key = dp.product_key
WHERE dp.product_key IS NULL
UNION ALL
SELECT 'Orphaned date keys',
       COUNT(*)
FROM fact_orders f
LEFT JOIN dim_date dd ON f.date_key = dd.date_key
WHERE dd.date_key IS NULL;
```

**When you will use this at work:** A late-arriving fact references a customer who has not been loaded into the dimension yet. Or a dimension cleanup accidentally deletes rows that the fact table still points to. Referential integrity checks catch broken joins before they turn into NULL values in dashboards.

**6. Business Rule Checks -- Do the numbers make sense?**

```sql
-- Revenue reconciliation: source vs warehouse
SELECT
    'Revenue reconciliation' AS check_name,
    ABS(source_total - warehouse_total) AS difference,
    CASE WHEN ABS(source_total - warehouse_total) < 0.01 THEN 'PASS' ELSE 'FAIL' END AS status
FROM (
    SELECT SUM(quantity * unit_price - discount) AS source_total FROM src_order_items
) src,
(
    SELECT SUM(revenue) AS warehouse_total FROM fact_orders
) wh;

-- Negative revenue check
SELECT 'Negative revenue' AS check_name,
       COUNT(*) AS violations
FROM fact_orders WHERE revenue < 0;

-- Future date check
SELECT 'Future order dates' AS check_name,
       COUNT(*) AS violations
FROM fact_orders f
JOIN dim_date d ON f.date_key = d.date_key
WHERE d.calendar_date > CURRENT_DATE;

-- Null measure check
SELECT 'Null revenues' AS check_name, COUNT(*) AS violations
FROM fact_orders WHERE revenue IS NULL
UNION ALL
SELECT 'Null quantities', COUNT(*)
FROM fact_orders WHERE quantity IS NULL;
```

**When you will use this at work:** Your pipeline computes revenue as `quantity * unit_price - discount`. A bug in the discount logic produces negative revenue for some rows. The revenue reconciliation catches it when the warehouse total does not match the source. Without this check, the finance team gets a report showing the company lost money last Tuesday.

### Reusable Quality Check Template

In production, combine all checks into a single quality report that runs after every load:

```sql
-- Master quality check: one query, all checks, clear pass/fail
WITH checks AS (
    -- Completeness
    SELECT 'NULL customer names' AS check_name, COUNT(*) AS violations
    FROM dim_customer WHERE name IS NULL AND is_current = TRUE
    UNION ALL
    -- Uniqueness
    SELECT 'Duplicate current customers', COUNT(*)
    FROM (
        SELECT customer_id FROM dim_customer
        WHERE is_current = TRUE
        GROUP BY customer_id HAVING COUNT(*) > 1
    ) d
    UNION ALL
    -- Referential integrity
    SELECT 'Orphaned customer keys', COUNT(*)
    FROM fact_orders f
    LEFT JOIN dim_customer dc ON f.customer_key = dc.customer_key
    WHERE dc.customer_key IS NULL
    UNION ALL
    -- Business rules
    SELECT 'Negative revenue', COUNT(*)
    FROM fact_orders WHERE revenue < 0
    UNION ALL
    SELECT 'Future dates', COUNT(*)
    FROM fact_orders f
    JOIN dim_date d ON f.date_key = d.date_key
    WHERE d.calendar_date > CURRENT_DATE
)
SELECT
    check_name,
    violations,
    CASE WHEN violations = 0 THEN 'PASS' ELSE 'FAIL' END AS status
FROM checks
ORDER BY violations DESC;
```

Your Airflow DAG runs this after every load. If any check returns FAIL, the DAG sends a Slack alert and optionally marks the load as failed so downstream tasks do not consume bad data.

> **Key Takeaway:** Data quality checks are production infrastructure, not optional polish. Run completeness, freshness, uniqueness, volume anomaly, referential integrity, and business rule checks after every load. A single quality report query with PASS/FAIL status makes monitoring straightforward.

---

## Module 2 Project: Incremental ETL Pipeline in Pure SQL

This project ties together every concept in the module. You will build a complete incremental ETL pipeline that loads a dimensional warehouse from a source system -- handling initial loads, SCD Type 2 changes, incremental fact loading, late-arriving data, and data quality checks. All in pure SQL.

### Project Setup

The companion code lives in:
- **Starter files:** `modules/module-2/starter/` -- schema definitions, source data for 3 simulated "days"
- **Solution files:** `modules/module-2/solution/` -- complete working code

Run the files in this order:

```bash
# Set up source tables and Day 1 data
psql -f starter/sample_data_day1.sql

# Set up the warehouse schema (dimensional model)
psql -f starter/warehouse_schema.sql
```

### The Warehouse Schema

The warehouse uses a classic star schema with SCD Type 2 dimensions:

```sql
CREATE TABLE dim_date (
    date_key        INT PRIMARY KEY,
    calendar_date   DATE NOT NULL UNIQUE,
    day_of_week     VARCHAR(10) NOT NULL,
    day_of_month    INT NOT NULL,
    month           INT NOT NULL,
    month_name      VARCHAR(10) NOT NULL,
    quarter         INT NOT NULL,
    year            INT NOT NULL,
    is_weekend      BOOLEAN NOT NULL,
    is_holiday      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE dim_customer (
    customer_key    SERIAL PRIMARY KEY,       -- surrogate key
    customer_id     INT NOT NULL,             -- natural key from source
    name            VARCHAR(200) NOT NULL,
    email           VARCHAR(200),
    city            VARCHAR(100),
    state           VARCHAR(50),
    country         VARCHAR(50) DEFAULT 'US',
    segment         VARCHAR(50),
    created_date    DATE,
    effective_date  DATE NOT NULL,            -- SCD Type 2: when this version became active
    expiry_date     DATE NOT NULL DEFAULT '9999-12-31',  -- SCD Type 2: when this version expired
    is_current      BOOLEAN NOT NULL DEFAULT TRUE         -- convenience flag
);

CREATE TABLE dim_product (
    product_key     SERIAL PRIMARY KEY,
    product_id      INT NOT NULL,
    product_name    VARCHAR(300) NOT NULL,
    category        VARCHAR(100),
    subcategory     VARCHAR(100),
    brand           VARCHAR(100),
    unit_cost       NUMERIC(10,2),
    unit_price      NUMERIC(10,2),
    effective_date  DATE NOT NULL,
    expiry_date     DATE NOT NULL DEFAULT '9999-12-31',
    is_current      BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE fact_orders (
    order_key       SERIAL PRIMARY KEY,
    order_id        INT NOT NULL,
    customer_key    INT NOT NULL REFERENCES dim_customer(customer_key),
    product_key     INT NOT NULL REFERENCES dim_product(product_key),
    date_key        INT NOT NULL REFERENCES dim_date(date_key),
    quantity        INT NOT NULL,
    unit_price      NUMERIC(10,2) NOT NULL,
    discount_amount NUMERIC(10,2) DEFAULT 0,
    revenue         NUMERIC(12,2) NOT NULL,
    cost            NUMERIC(12,2),
    profit          NUMERIC(12,2),
    order_status    VARCHAR(20)
);

CREATE INDEX idx_fact_orders_date ON fact_orders(date_key);
CREATE INDEX idx_fact_orders_customer ON fact_orders(customer_key);
CREATE INDEX idx_fact_orders_product ON fact_orders(product_key);
```

Notice the SCD Type 2 fields: `effective_date`, `expiry_date`, `is_current`. The `expiry_date` defaults to '9999-12-31' (far future) for current rows. The surrogate `customer_key` / `product_key` is SERIAL, auto-assigned by Postgres for each version of the record.

### Step 1: Initial Load (01_initial_load.sql)

Populate all dimensions and facts from the Day 1 snapshot:

```sql
-- 1. Populate dim_date (generate a full calendar)
INSERT INTO dim_date (date_key, calendar_date, day_of_week, day_of_month,
                      month, month_name, quarter, year, is_weekend, is_holiday)
SELECT
    TO_CHAR(d, 'YYYYMMDD')::INT,
    d,
    TRIM(TO_CHAR(d, 'Day')),
    EXTRACT(DAY FROM d),
    EXTRACT(MONTH FROM d),
    TRIM(TO_CHAR(d, 'Month')),
    EXTRACT(QUARTER FROM d),
    EXTRACT(YEAR FROM d),
    EXTRACT(ISODOW FROM d) IN (6, 7),
    FALSE
FROM generate_series('2024-01-01'::date, '2026-12-31'::date, '1 day') AS d;

-- 2. Initial load dim_customer
INSERT INTO dim_customer (customer_id, name, email, city, state, country,
                          segment, created_date, effective_date)
SELECT id, name, email, city, state, 'US', segment,
       created_at::date, created_at::date
FROM src_customers;

-- 3. Initial load dim_product
INSERT INTO dim_product (product_id, product_name, category, subcategory,
                         brand, unit_cost, unit_price, effective_date)
SELECT id, product_name, category, subcategory, brand,
       unit_cost, unit_price, created_at::date
FROM src_products;

-- 4. Initial load fact_orders
INSERT INTO fact_orders (order_id, customer_key, product_key, date_key,
                         quantity, unit_price, discount_amount,
                         revenue, cost, profit, order_status)
SELECT
    o.id,
    dc.customer_key,
    dp.product_key,
    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    (oi.quantity * oi.unit_price - oi.discount),
    (oi.quantity * dp.unit_cost),
    (oi.quantity * oi.unit_price - oi.discount) - (oi.quantity * dp.unit_cost),
    o.status
FROM src_orders o
JOIN src_order_items oi ON o.id = oi.order_id
JOIN dim_customer dc ON o.customer_id = dc.customer_id AND dc.is_current = TRUE
JOIN dim_product dp ON oi.product_id = dp.product_id AND dp.is_current = TRUE;
```

The key insight in the fact load: we join to `dim_customer` and `dim_product` with `is_current = TRUE` to get the correct surrogate keys. The fact table stores surrogate keys, not natural keys, so it can point to the right version of each dimension record.

### Step 2: Simulate Day 2 Changes, Then Run Incremental Dimensions (02_incremental_dimensions.sql)

```bash
# Load Day 2 changes into the source tables
psql -f starter/sample_data_day2.sql
```

Day 2 brings:
- Customer 1 (Alice) moved from New York to Boston
- Customer 5 (Eve) changed segment from SMB to Enterprise
- Two new customers (Karen, Leo)
- Product 3 price increased from $19.99 to $24.99
- Two new products (Bluetooth Speaker, Winter Jacket)
- New orders, order status updates

Now run the SCD Type 2 incremental load:

```sql
-- SCD Type 2: Customer Dimension
-- Step 1: Expire current rows where tracked attributes changed
UPDATE dim_customer dc
SET expiry_date = src.updated_at::date - 1,
    is_current = FALSE
FROM src_customers src
WHERE dc.customer_id = src.id
  AND dc.is_current = TRUE
  AND src.updated_at > '2025-01-10'  -- since last load
  AND (dc.city != src.city OR dc.state != src.state OR dc.segment != src.segment);

-- Step 2: Insert new current rows for changed customers
INSERT INTO dim_customer (customer_id, name, email, city, state, country,
                          segment, created_date, effective_date)
SELECT src.id, src.name, src.email, src.city, src.state, 'US',
       src.segment, src.created_at::date, src.updated_at::date
FROM src_customers src
WHERE src.updated_at > '2025-01-10'
  AND (
    EXISTS (
        SELECT 1 FROM dim_customer dc
        WHERE dc.customer_id = src.id AND dc.is_current = FALSE
          AND dc.expiry_date = src.updated_at::date - 1
    )
    OR NOT EXISTS (
        SELECT 1 FROM dim_customer dc WHERE dc.customer_id = src.id
    )
  );

-- Step 3: Type 1 update for non-tracked attributes (email)
UPDATE dim_customer dc
SET email = src.email
FROM src_customers src
WHERE dc.customer_id = src.id
  AND dc.is_current = TRUE
  AND dc.email != src.email;
```

After this runs, `dim_customer` will have:
- Alice: 2 rows (New York expired, Boston current)
- Eve: 2 rows (SMB expired, Enterprise current)
- Karen and Leo: 1 row each (new customers)
- Everyone else: 1 row, unchanged

The same pattern applies to products (Product 3 gets a new row for the price change, new products get inserted).

### Step 3: Incremental Fact Loading (03_incremental_facts.sql)

```sql
-- Load new orders, looking up current dimension keys
INSERT INTO fact_orders (order_id, customer_key, product_key, date_key,
                         quantity, unit_price, discount_amount,
                         revenue, cost, profit, order_status)
SELECT
    o.id,
    dc.customer_key,
    dp.product_key,
    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    (oi.quantity * oi.unit_price - oi.discount),
    (oi.quantity * dp.unit_cost),
    (oi.quantity * oi.unit_price - oi.discount) - (oi.quantity * dp.unit_cost),
    o.status
FROM src_orders o
JOIN src_order_items oi ON o.id = oi.order_id
JOIN dim_customer dc ON o.customer_id = dc.customer_id AND dc.is_current = TRUE
JOIN dim_product dp ON oi.product_id = dp.product_id AND dp.is_current = TRUE
-- Only new orders (not already loaded)
WHERE NOT EXISTS (
    SELECT 1 FROM fact_orders f WHERE f.order_id = o.id
);

-- Update status for orders that changed (e.g., pending -> completed)
UPDATE fact_orders f
SET order_status = o.status
FROM src_orders o
WHERE f.order_id = o.id
  AND f.order_status != o.status;
```

The `NOT EXISTS` clause is the incremental logic -- it only loads orders that are not already in the fact table. This is idempotent: you can safely run it twice and it will not create duplicates.

The status UPDATE handles order lifecycle changes. When order 5 went from 'pending' to 'completed', we update the existing fact row rather than creating a new one. Order status is a Type 1 attribute on the fact table.

### Step 4: Late-Arriving Facts (04_late_arriving.sql)

Late-arriving facts are orders whose `order_date` is in the past but that arrive in the source system today. The critical question: which dimension version was active when the order was placed?

```sql
-- Late-arriving fact load with point-in-time dimension lookup
INSERT INTO fact_orders (order_id, customer_key, product_key, date_key,
                         quantity, unit_price, discount_amount,
                         revenue, cost, profit, order_status)
SELECT
    o.id,
    dc.customer_key,
    dp.product_key,
    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    (oi.quantity * oi.unit_price - oi.discount),
    (oi.quantity * dp.unit_cost),
    (oi.quantity * oi.unit_price - oi.discount) - (oi.quantity * dp.unit_cost),
    o.status
FROM src_orders o
JOIN src_order_items oi ON o.id = oi.order_id
-- Point-in-time lookup: which customer row was active on the order date?
JOIN dim_customer dc ON o.customer_id = dc.customer_id
    AND o.order_date::date BETWEEN dc.effective_date AND dc.expiry_date
-- Point-in-time lookup: which product row was active on the order date?
JOIN dim_product dp ON oi.product_id = dp.product_id
    AND o.order_date::date BETWEEN dp.effective_date AND dp.expiry_date
WHERE NOT EXISTS (
    SELECT 1 FROM fact_orders f WHERE f.order_id = o.id
);
```

**The key difference:** Instead of `dc.is_current = TRUE`, we join on `o.order_date BETWEEN dc.effective_date AND dc.expiry_date`. This finds the dimension version that was active at the time the order was placed.

**Production scenario:** Order 11 was placed on January 6 but arrives in the source system on January 12 (Day 3). By January 12, Alice has already moved from New York to Boston (Day 2 change). If we joined on `is_current = TRUE`, we would attribute this January 6 order to Alice-in-Boston. But Alice was still in New York on January 6. The point-in-time join correctly assigns Alice-in-New-York's surrogate key.

**Fallback for missing dimension rows:**

Sometimes the dimension record for the order date does not exist yet (the dimension arrived *after* the fact). The fallback uses `JOIN LATERAL` to find the earliest known dimension record:

```sql
-- Fallback: use the earliest known dimension record
INSERT INTO fact_orders (order_id, customer_key, product_key, date_key,
                         quantity, unit_price, discount_amount,
                         revenue, cost, profit, order_status)
SELECT
    o.id,
    dc.customer_key,
    dp.product_key,
    TO_CHAR(o.order_date, 'YYYYMMDD')::INT,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    (oi.quantity * oi.unit_price - oi.discount),
    (oi.quantity * dp.unit_cost),
    (oi.quantity * oi.unit_price - oi.discount) - (oi.quantity * dp.unit_cost),
    o.status
FROM src_orders o
JOIN src_order_items oi ON o.id = oi.order_id
JOIN LATERAL (
    SELECT customer_key FROM dim_customer
    WHERE customer_id = o.customer_id
    ORDER BY effective_date LIMIT 1
) dc ON TRUE
JOIN LATERAL (
    SELECT product_key, unit_cost FROM dim_product
    WHERE product_id = oi.product_id
    ORDER BY effective_date LIMIT 1
) dp ON TRUE
WHERE NOT EXISTS (
    SELECT 1 FROM fact_orders f WHERE f.order_id = o.id
);
```

### Step 5: Data Quality Checks (05_quality_checks.sql)

After every load, run the full quality suite:

```sql
-- 1. Orphaned fact records (missing dimension keys)
SELECT 'Orphaned customer keys' AS check_name,
       COUNT(*) AS violations
FROM fact_orders f
LEFT JOIN dim_customer dc ON f.customer_key = dc.customer_key
WHERE dc.customer_key IS NULL
UNION ALL
SELECT 'Orphaned product keys',
       COUNT(*)
FROM fact_orders f
LEFT JOIN dim_product dp ON f.product_key = dp.product_key
WHERE dp.product_key IS NULL
UNION ALL
SELECT 'Orphaned date keys',
       COUNT(*)
FROM fact_orders f
LEFT JOIN dim_date dd ON f.date_key = dd.date_key
WHERE dd.date_key IS NULL;

-- 2. Duplicate dimension entries (same natural key marked as current)
SELECT 'Duplicate current customers' AS check_name,
       COUNT(*) AS violations
FROM (
    SELECT customer_id, COUNT(*) AS cnt
    FROM dim_customer WHERE is_current = TRUE
    GROUP BY customer_id HAVING COUNT(*) > 1
) dupes
UNION ALL
SELECT 'Duplicate current products',
       COUNT(*)
FROM (
    SELECT product_id, COUNT(*) AS cnt
    FROM dim_product WHERE is_current = TRUE
    GROUP BY product_id HAVING COUNT(*) > 1
) dupes;

-- 3. Revenue reconciliation: source vs warehouse
SELECT
    'Revenue reconciliation' AS check_name,
    ABS(source_total - warehouse_total) AS difference,
    CASE WHEN ABS(source_total - warehouse_total) < 0.01 THEN 'PASS' ELSE 'FAIL' END AS status
FROM (
    SELECT SUM(quantity * unit_price - discount) AS source_total FROM src_order_items
) src,
(
    SELECT SUM(revenue) AS warehouse_total FROM fact_orders
) wh;

-- 4. Negative revenue check
SELECT 'Negative revenue' AS check_name,
       COUNT(*) AS violations
FROM fact_orders WHERE revenue < 0;

-- 5. Future date check
SELECT 'Future order dates' AS check_name,
       COUNT(*) AS violations
FROM fact_orders f
JOIN dim_date d ON f.date_key = d.date_key
WHERE d.calendar_date > CURRENT_DATE;

-- 6. Null measure check
SELECT 'Null revenues' AS check_name, COUNT(*) AS violations
FROM fact_orders WHERE revenue IS NULL
UNION ALL
SELECT 'Null quantities', COUNT(*)
FROM fact_orders WHERE quantity IS NULL;
```

All violations should be zero. If any are not, investigate before signing off on the load.

### Running the Full Pipeline

```bash
# Day 1: Initial load
psql -f starter/sample_data_day1.sql
psql -f starter/warehouse_schema.sql
psql -f solution/01_initial_load.sql
psql -f solution/05_quality_checks.sql   # verify

# Day 2: Incremental load with SCD changes
psql -f starter/sample_data_day2.sql
psql -f solution/02_incremental_dimensions.sql
psql -f solution/03_incremental_facts.sql
psql -f solution/05_quality_checks.sql   # verify

# Day 3: Late-arriving data
psql -f starter/sample_data_day3.sql
psql -f solution/02_incremental_dimensions.sql   # handle new dimension changes
psql -f solution/04_late_arriving.sql             # handle late-arriving facts
psql -f solution/03_incremental_facts.sql         # handle normal new facts
psql -f solution/05_quality_checks.sql            # verify
```

This is the exact sequence your Airflow DAG would orchestrate in production. Each step is idempotent (safe to re-run). The quality checks gate downstream consumption.

> **Key Takeaway:** This project is a complete, production-style incremental ETL pipeline written in pure SQL. It handles initial loads, SCD Type 2 dimension changes, incremental fact loading, late-arriving data with point-in-time dimension lookups, and automated data quality checks. These are the exact patterns you will build and maintain on the job.

---

## What's Next

You now have the SQL toolkit that data engineers use daily -- CTEs for readable transformations, window functions for analytics and dedup, UPSERT/MERGE for incremental loading, SCD Type 2 for dimension history, performance tuning with indexes and partitioning, and automated data quality checks. In Module 3, we move from *how to write the SQL* to *where to store the data* -- storage engines, columnar formats, table formats like Delta Lake and Apache Iceberg, and the architecture decisions that determine whether your warehouse costs $500/month or $50,000/month.
